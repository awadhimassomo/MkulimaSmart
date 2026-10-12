"""
Placing a website order, and deciding who delivers each line.

A product the seller delivers itself goes to that seller. A product "sold through agents" (a supplier that sells wholesale
only) goes to the supplier's retail agent for the delivery region the buyer chose. If the supplier has no agent there, the
line goes to the supplier, who is emailed about the demand and can ask Mkulima Smart to deliver it.
"""
import logging

from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q

from .models import Order, OrderLine

logger = logging.getLogger(__name__)


def route(product, quantity, region):
    """Returns (user who delivers, route) for one product bought for delivery in `region`."""
    if not product.sold_through_agents:
        return product.supplier, OrderLine.ROUTE_SELLER

    from inputs.models import RetailAgent, ShopStockItem, WholesaleProduct
    from operations.models import InputSeller

    supplier = InputSeller.objects.filter(user=product.supplier).first()
    agents = []
    if supplier is not None:
        links = RetailAgent.objects.filter(supplier=supplier, region=region).select_related("agent__user")
        agents = [link.agent for link in links if link.agent.user_id and link.agent.is_active]
    if not agents:
        return product.supplier, OrderLine.ROUTE_NO_AGENT

    wholesale = WholesaleProduct.objects.filter(marketplace_product=product).first()

    def can_supply(agent):
        if wholesale is None:
            return False
        return ShopStockItem.objects.filter(shop=agent, wholesale_product=wholesale, is_active=True, quantity__gte=quantity).exists()

    def open_lines(agent):
        return OrderLine.objects.filter(fulfilled_by=agent.user, status__in=["new", "confirmed"]).count()

    # An agent who has it in stock first; among equals, the one with the least waiting to deliver.
    best = min(agents, key=lambda agent: (not can_supply(agent), open_lines(agent), agent.pk))
    return best.user, OrderLine.ROUTE_AGENT


@transaction.atomic
def place_order(user, cart, *, name, phone, address, town, region, notes, total, delivery_option="", delivery_fee=0, vat_amount=0):
    """Create the order and one line per cart item, routed. The caller clears the cart."""
    shipping = ", ".join(part for part in (address, town, region) if part)
    order = Order.objects.create(
        user=user, total_amount=total, shipping_address=shipping, phone_number=phone[:15],
        buyer_name=name[:150], delivery_region=region, delivery_notes=notes,
        delivery_option=delivery_option, delivery_fee=delivery_fee, vat_amount=vat_amount,
    )
    for item in cart.items.select_related("product__supplier", "product__category"):
        product = item.product
        price = product.discount_price or product.price
        deliverer, kind = route(product, item.quantity, region)
        OrderLine.objects.create(
            order=order, product=product, product_name=product.name, brand=product.brand, quantity=item.quantity,
            unit_price=price, seller=product.supplier, fulfilled_by=deliverer, route=kind, region=region,
        )
    return order


# ---------------------------------------------------------------------------
# Telling the people who have to act
# ---------------------------------------------------------------------------

def _lines_text(lines):
    return "\n".join(f"- {line.quantity} x {line.product_name}{' (' + line.brand + ')' if line.brand else ''} at TSh {line.unit_price:,.0f}" for line in lines)


def _buyer_text(order):
    return f"Buyer: {order.buyer_name or order.user.get_full_name() or 'Mkulima Smart customer'}\nPhone: {order.phone_number}\nDeliver to: {order.shipping_address}"


def notify(order):
    """Email whoever has to deliver (agent or seller), and the supplier when there is no agent. Never raises."""
    try:
        by_user = {}
        for line in order.lines.select_related("fulfilled_by", "seller"):
            if line.fulfilled_by and line.fulfilled_by.email:
                by_user.setdefault(line.fulfilled_by, []).append(line)
        for recipient, lines in by_user.items():
            no_agent = [line for line in lines if line.route == OrderLine.ROUTE_NO_AGENT]
            if no_agent:
                subject = f"Demand in {order.delivery_region} with no agent: order #{order.pk}"
                intro = (
                    f"A farmer in {order.delivery_region} ordered your products, but you have no retail agent there yet. "
                    "You can deliver it yourself or ask Mkulima Smart to deliver it for you from your Website Orders page, "
                    "and you can appoint an agent for the region from Retail Agents."
                )
            else:
                subject = f"New website order #{order.pk} for you to deliver"
                intro = "A customer ordered these from the Mkulima Smart website. Please confirm it from your Website Orders page."
            body = f"{intro}\n\n{_lines_text(lines)}\n\n{_buyer_text(order)}\n\nMkulima Smart"
            send_mail(subject, body, None, [recipient.email], fail_silently=True)
    except Exception:
        logger.exception("Could not email the people to deliver order %s", order.pk)

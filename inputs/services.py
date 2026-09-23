"""
Stock-changing operations. Every change to ShopStockItem.quantity goes through
here so it is atomic, row-locked and recorded as a StockMovement.
"""
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import (
    FarmerOrder,
    FarmerOrderItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    ShopStockItem,
    StockMovement,
    WholesaleProduct,
)
from .signals import farmer_order_status_changed

ZERO = Decimal("0")


class StockError(Exception):
    """Raised when an operation would leave stock in an invalid state."""


def _to_decimal(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise StockError(f"Invalid {field}.")
    if not number.is_finite():
        raise StockError(f"Invalid {field}.")
    return number


def _move(item, change, reason, user=None, reference="", note=""):
    """Apply a quantity change to an already-locked stock item."""
    new_quantity = item.quantity + change
    if new_quantity < 0:
        raise StockError(f"Not enough stock for {item.name}: {item.quantity} available.")
    item.quantity = new_quantity
    item.save(update_fields=["quantity", "updated_at"])
    StockMovement.objects.create(
        stock_item=item,
        reason=reason,
        change=change,
        balance_after=new_quantity,
        reference=reference,
        note=note[:255],
        created_by=user,
    )


@transaction.atomic
def record_opening_stock(item, user=None):
    if item.quantity:
        StockMovement.objects.create(
            stock_item=item, reason="opening", change=item.quantity, balance_after=item.quantity, created_by=user
        )


@transaction.atomic
def adjust_stock(shop, item_id, change, user=None, note=""):
    change = _to_decimal(change, "quantity")
    if change == 0:
        raise StockError("Adjustment cannot be zero.")
    item = ShopStockItem.objects.select_for_update().get(pk=item_id, shop=shop)
    _move(item, change, "adjustment", user=user, note=note)
    return item


@transaction.atomic
def record_sale(shop, lines, user=None, payment_method="cash", discount=0, amount_paid=None,
                customer_name="", customer_phone=""):
    """
    lines: iterable of {"stock_item": id, "quantity": number, "unit_price": optional number}.
    Prices default to the stock item's selling price.
    """
    if not lines:
        raise StockError("The cart is empty.")
    if payment_method not in dict(Sale.POS_PAYMENT_CHOICES):
        raise StockError("Choose a valid payment method.")

    # Merge duplicate lines and lock rows in a stable order to avoid deadlocks.
    quantities = {}
    prices = {}
    for line in lines:
        try:
            item_id = int(line.get("stock_item"))
        except (TypeError, ValueError):
            raise StockError("Invalid product in cart.")
        quantity = _to_decimal(line.get("quantity"), "quantity")
        if quantity <= 0:
            raise StockError("Quantities must be greater than zero.")
        quantities[item_id] = quantities.get(item_id, ZERO) + quantity
        if line.get("unit_price") not in (None, ""):
            price = _to_decimal(line["unit_price"], "price")
            if price < 0:
                raise StockError("Prices cannot be negative.")
            prices[item_id] = price

    items = {
        item.pk: item
        for item in ShopStockItem.objects.select_for_update().filter(pk__in=quantities, shop=shop, is_active=True).order_by("pk")
    }
    if len(items) != len(quantities):
        raise StockError("Some products in the cart are no longer available.")

    discount = _to_decimal(discount or 0, "discount")
    subtotal = sum(
        (prices.get(item_id, items[item_id].selling_price) * qty for item_id, qty in quantities.items()), ZERO
    )
    if discount < 0 or discount > subtotal:
        raise StockError("Discount must be between zero and the subtotal.")
    total = subtotal - discount
    paid = total if amount_paid in (None, "") else _to_decimal(amount_paid, "amount paid")
    if payment_method != "credit" and paid < total:
        raise StockError("Amount paid is less than the total. Use the Credit payment method for unpaid sales.")

    customer_phone = customer_phone.strip()
    if customer_phone.lstrip("+") == "255":
        # The site-wide phone script pre-fills "+255" into empty tel inputs.
        customer_phone = ""

    sale = Sale.objects.create(
        shop=shop,
        payment_method=payment_method,
        subtotal=subtotal,
        discount=discount,
        total=total,
        amount_paid=paid,
        customer_name=customer_name.strip()[:120],
        customer_phone=customer_phone[:30],
        sold_by=user,
    )
    for item_id, qty in quantities.items():
        item = items[item_id]
        unit_price = prices.get(item_id, item.selling_price)
        SaleItem.objects.create(
            sale=sale,
            stock_item=item,
            product_name=item.name,
            quantity=qty,
            unit_price=unit_price,
            cost_price=item.cost_price,
            line_total=unit_price * qty,
        )
        _move(item, -qty, "sale", user=user, reference=sale.receipt_number)
    return sale


@transaction.atomic
def create_purchase_order(shop, manufacturer, quantities, user=None, notes=""):
    """quantities: {wholesale_product_id: int quantity}; zero quantities are ignored."""
    quantities = {pid: qty for pid, qty in quantities.items() if qty}
    if not quantities:
        raise StockError("Add at least one product to the order.")

    products = {
        p.pk: p
        for p in WholesaleProduct.objects.filter(pk__in=quantities, manufacturer=manufacturer, is_active=True)
    }
    if len(products) != len(quantities):
        raise StockError("Some products are no longer available from this manufacturer.")
    for pid, qty in quantities.items():
        if qty < products[pid].min_order_quantity:
            raise StockError(f"Minimum order for {products[pid].name} is {products[pid].min_order_quantity}.")

    order = PurchaseOrder.objects.create(shop=shop, manufacturer=manufacturer, notes=notes, created_by=user)
    for pid, qty in quantities.items():
        product = products[pid]
        PurchaseOrderItem.objects.create(
            order=order, wholesale_product=product, product_name=str(product), quantity=qty, unit_price=product.wholesale_price
        )
    order.recalculate_total()
    return order


# Which status each role may move an order to, from which current statuses.
MANUFACTURER_TRANSITIONS = {
    "confirmed": {"pending"},
    "dispatched": {"pending", "confirmed"},
    "cancelled": {"pending", "confirmed"},
}
SHOP_TRANSITIONS = {
    "cancelled": {"pending"},
}


@transaction.atomic
def manufacturer_update_order(order, new_status, note=""):
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status not in MANUFACTURER_TRANSITIONS.get(new_status, set()):
        raise StockError(f"Cannot mark a {order.get_status_display().lower()} order as {new_status}.")

    if new_status == "dispatched":
        items = list(order.items.all())
        products = {
            p.pk: p
            for p in WholesaleProduct.objects.select_for_update().filter(pk__in=[i.wholesale_product_id for i in items])
        }
        for item in items:
            product = products.get(item.wholesale_product_id)
            if product is None:
                continue
            if product.stock_available < item.quantity:
                raise StockError(f"Only {product.stock_available} of {product.name} in your stock.")
            product.stock_available -= item.quantity
            product.save(update_fields=["stock_available", "updated_at"])

    order.status = new_status
    if note:
        order.manufacturer_note = note
    order.save(update_fields=["status", "manufacturer_note", "updated_at"])
    return order


@transaction.atomic
def shop_cancel_order(order):
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status not in SHOP_TRANSITIONS["cancelled"]:
        raise StockError("Only pending orders can be cancelled. Contact the manufacturer.")
    order.status = "cancelled"
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def receive_purchase_order(order, user=None):
    """Shop confirms delivery: add every line to shop stock, creating stock items as needed."""
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != "dispatched":
        raise StockError("Only dispatched orders can be marked as received.")

    for line in order.items.select_related("wholesale_product"):
        product = line.wholesale_product
        item = None
        if product is not None:
            item = ShopStockItem.objects.select_for_update().filter(shop=order.shop, wholesale_product=product).first()
        if item is None:
            item = ShopStockItem.objects.create(
                shop=order.shop,
                wholesale_product=product,
                name=line.product_name,
                brand=product.brand if product else "",
                category=product.category if product else "other",
                unit=product.unit if product else "piece",
                cost_price=line.unit_price,
                selling_price=(product.suggested_retail_price if product and product.suggested_retail_price else line.unit_price),
                quantity=ZERO,
            )
            _copy_catalog_image(item, product)
        else:
            item.cost_price = line.unit_price
            item.is_active = True
            item.save(update_fields=["cost_price", "is_active", "updated_at"])
            if not item.image:
                _copy_catalog_image(item, product)
        _move(item, Decimal(line.quantity), "restock", user=user, reference=order.order_number)

    order.status = "received"
    order.received_at = timezone.now()
    order.save(update_fields=["status", "received_at", "updated_at"])
    return order


def _copy_catalog_image(item, product):
    """Give a new shop stock item the manufacturer's primary product photo."""
    source = product.primary_image if product else None
    if source is None or not source.image:
        return
    try:
        with source.image.open("rb") as handle:
            name = source.image.name.rsplit("/", 1)[-1]
            item.image.save(name, ContentFile(handle.read()), save=True)
    except (OSError, ValueError):
        # A missing file on disk should not block receiving stock.
        pass


# ---------------------------------------------------------------------------
# Farmer orders (placed via Kikapu WhatsApp)
# ---------------------------------------------------------------------------

class OutOfStockError(StockError):
    """The order can't be fulfilled right now (sold out, expired, shop paused). Callers answer 409."""


def _whole(quantity):
    return int(quantity) if quantity == int(quantity) else quantity


@transaction.atomic
def create_farmer_order(shop, quantities, *, external_order_id, farmer_name, farmer_phone,
                        delivery_region="", delivery_notes="", farmer_user=None, channel="kikapu"):
    """
    quantities: {stock_item_id: quantity}. Re-checks stock under a row lock and reserves it,
    so a POS sale a minute later can't sell the same units.
    """
    if not quantities:
        raise StockError("The order has no items.")
    if not (shop.is_active and shop.list_on_kikapu):
        raise OutOfStockError(f"{shop} is not taking orders right now.")

    items = {
        item.pk: item
        for item in ShopStockItem.objects.select_for_update().filter(pk__in=quantities, shop=shop).order_by("pk")
    }
    unknown = [pk for pk in quantities if pk not in items]
    if unknown:
        raise StockError(f"input-{unknown[0]} is not sold by this shop.")

    for pk, qty in quantities.items():
        item = items[pk]
        if not item.is_active or item.is_expired:
            raise OutOfStockError(f"{item.name} is no longer available at {shop}.")
        if item.quantity < qty:
            available = _whole(item.quantity)
            raise OutOfStockError(
                f"Only {available} {item.get_unit_display().lower()} of {item.name} left at {shop}."
                if available > 0 else f"{item.name} is sold out at {shop}."
            )

    order = FarmerOrder.objects.create(
        shop=shop,
        channel=channel,
        external_order_id=external_order_id,
        farmer_name=farmer_name.strip()[:120],
        farmer_phone=farmer_phone.strip()[:30],
        farmer_user=farmer_user,
        delivery_region=delivery_region.strip()[:60],
        delivery_notes=delivery_notes.strip(),
    )
    total = ZERO
    for pk, qty in quantities.items():
        item = items[pk]
        line_total = item.selling_price * qty
        total += line_total
        FarmerOrderItem.objects.create(
            order=order, stock_item=item, product_name=item.name, quantity=qty,
            unit_price=item.selling_price, cost_price=item.cost_price, line_total=line_total,
        )
        _move(item, -qty, "farmer_order", reference=order.order_number)
    order.total = total
    order.save(update_fields=["total", "updated_at"])
    return order


@transaction.atomic
def update_farmer_order_status(order, new_status, user=None, note=""):
    """Move a farmer order along; cancelling returns reserved stock, delivering records the sale."""
    order = FarmerOrder.objects.select_for_update().get(pk=order.pk)
    if new_status not in order.allowed_next_statuses:
        raise StockError(f"A {order.get_status_display().lower()} order can't be marked {new_status}.")

    lines = list(order.items.all())
    if new_status == "cancelled":
        stock = {
            item.pk: item
            for item in ShopStockItem.objects.select_for_update().filter(pk__in=[l.stock_item_id for l in lines if l.stock_item_id])
        }
        for line in lines:
            if line.stock_item_id in stock:
                _move(stock[line.stock_item_id], line.quantity, "order_cancelled", user=user,
                      reference=order.order_number, note=note)

    if new_status == "delivered":
        # Stock left the shelf when the order was accepted, so the sale doesn't move stock again.
        sale = Sale.objects.create(
            shop=order.shop, channel="kikapu", payment_method="on_delivery",
            subtotal=order.total, total=order.total, amount_paid=order.total,
            customer_name=order.farmer_name, customer_phone=order.farmer_phone, sold_by=user,
        )
        for line in lines:
            SaleItem.objects.create(
                sale=sale, stock_item=line.stock_item, product_name=line.product_name, quantity=line.quantity,
                unit_price=line.unit_price, cost_price=line.cost_price, line_total=line.line_total,
            )
        order.sale = sale

    order.status = new_status
    order.shop_note = note.strip()[:255]
    order.save(update_fields=["status", "shop_note", "sale", "updated_at"])
    farmer_order_status_changed.send(sender=FarmerOrder, order=order, status=new_status, note=order.shop_note)
    return order

"""
Put a product that is already in a seller's Catalog (manufacturers) or Stock (shops) on the website marketplace with one
click, instead of typing it in again as a new listing.

The marketplace listing (website.Product) is created from the product's own details, linked to it, and kept in step:
whenever the price or quantity of the original changes, the listing's price and stock follow. "Hide" switches the listing
off without deleting it, and listing it again switches the same listing back on.
"""
import os

from django.core.files.base import ContentFile
from django.db import transaction

from marketplace.forms import generate_unique_slug
from website.models import Category, Product, ProductImage

# Which website category each kind of input belongs to.
CATEGORIES = {
    "seedlings": ("seedlings-nursery", "Seedlings & Nursery"),
    "fertilizer": ("fertilizers", "Fertilizers"),
    "compost": ("soil-health", "Soil Health"),
    "seeds": ("seeds", "Seeds"),
    "pesticides": ("crop-protection", "Crop Protection"),
    "tools": ("farm-tools", "Farm Tools"),
    "feed": ("animal-feed", "Animal Feed"),
    "other": ("other-inputs", "Other Inputs"),
}


class ListingError(Exception):
    """Something the seller can fix; the message is shown to them."""


def _category(key):
    slug, name = CATEGORIES.get(key, CATEGORIES["other"])
    category, _ = Category.objects.get_or_create(slug=slug, defaults={"name": name, "is_active": True})
    return category


def is_listed(obj):
    product = obj.marketplace_product
    return bool(product and product.is_active)


# ---------------------------------------------------------------------------
# What the listing says
# ---------------------------------------------------------------------------

def _facts(wholesale):
    facts = []
    if wholesale is not None:
        if wholesale.pack_size:
            facts.append(f"Pack size: {wholesale.pack_size}")
        if wholesale.composition:
            facts.append(f"Composition: {wholesale.composition}")
        if wholesale.seed_variety:
            facts.append(f"Variety: {wholesale.seed_variety}")
        if wholesale.maturity_days:
            facts.append(f"Matures in about {wholesale.maturity_days} days")
        if wholesale.target_crops:
            facts.append("Suitable crops: " + ", ".join(wholesale.target_crops))
        if wholesale.suitable_regions_display:
            facts.append("Suitable regions: " + wholesale.suitable_regions_display)
        if wholesale.soil_type_display:
            facts.append("Soil: " + wholesale.soil_type_display)
    return facts


def _description(name, wholesale, agent_of=None):
    parts = []
    if wholesale is not None and wholesale.description:
        parts.append(wholesale.description.strip())
    facts = _facts(wholesale)
    if facts:
        parts.append("\n".join(facts))
    if wholesale is not None and wholesale.usage_instructions:
        parts.append("How to use: " + wholesale.usage_instructions.strip())
    if agent_of is not None:
        parts.append(f"Sold by an authorized retail agent of {agent_of}.")
    return "\n\n".join(parts) or name


def _copy_image(product, source):
    """Use the product's photo as the listing's cover photo (only when the listing has none yet)."""
    if not source or product.images.exists():
        return
    try:
        source.open("rb")
        data = source.read()
        source.close()
    except Exception:
        return
    image = ProductImage(product=product, is_primary=True)
    image.image.save(os.path.basename(source.name), ContentFile(data), save=True)


@transaction.atomic
def _publish(obj, user, name, brand, category_key, description, price, stock, photo):
    product = obj.marketplace_product
    if product is None:
        product = Product(
            name=name[:200], brand=(brand or "")[:120], category=_category(category_key), description=description, price=price, stock=stock,
            supplier=user, is_active=True,
        )
        product.slug = generate_unique_slug(product.name, product)
        product.save()
        obj.marketplace_product = product
        obj.save(update_fields=["marketplace_product"])
    else:
        # Listing again refreshes price and stock and switches it back on; the seller's edits to the text are kept.
        Product.objects.filter(pk=product.pk).update(price=price, stock=stock, is_active=True)
        product.refresh_from_db()
    _copy_image(product, photo)
    return product


# ---------------------------------------------------------------------------
# One product
# ---------------------------------------------------------------------------

WHOLESALE_ONLY = (
    "You are set up as wholesale only, so your products are not shown to farmers on the website. "
    "If you also sell to farmers directly, switch that on first."
)


def publish_stock_item(item):
    """List a shop's stock item on the marketplace."""
    if not item.shop.retails:
        raise ListingError(WHOLESALE_ONLY)
    user = item.shop.user
    if user is None:
        raise ListingError("This shop has no login account, so it cannot list products on the website.")
    if not item.is_active:
        raise ListingError(f"{item.name} is switched off in your stock. Switch it on first.")
    if item.is_expired:
        raise ListingError(f"{item.name} is past its expiry date, so it was not listed.")
    wholesale = item.wholesale_product
    agent_of = None
    if wholesale is not None:
        maker = wholesale.manufacturer
        is_agent = maker.retail_agents.filter(agent=item.shop).exists()
        if not maker.retails and not is_agent:
            raise ListingError(
                f"{maker} sells wholesale only. Ask them to appoint you as a retail agent to list their products on the website."
            )
        agent_of = maker if is_agent else None
    photo = item.image or (wholesale.primary_image.image if wholesale and wholesale.primary_image else None)
    return _publish(
        item, user, item.name, item.brand or (wholesale.brand if wholesale else ""), item.category, _description(item.name, wholesale, agent_of),
        item.selling_price, max(0, int(item.quantity)), photo,
    )


def publish_wholesale(product):
    """List a manufacturer's catalog product on the marketplace, at its suggested retail price."""
    if not product.manufacturer.retails:
        raise ListingError(WHOLESALE_ONLY)
    user = product.manufacturer.user
    if user is None:
        raise ListingError("This company has no login account, so it cannot list products on the website.")
    if not product.is_active:
        raise ListingError(f"{product.name} is hidden in your catalog. Make it visible first.")
    price = product.suggested_retail_price or product.wholesale_price
    image = product.primary_image
    return _publish(
        product, user, product.name, product.brand, product.category, _description(product.name, product),
        price, product.stock_available, image.image if image else None,
    )


def hide(obj):
    """Switch the website listing off (it is kept, so it can be switched back on). Returns False if there was none."""
    if not obj.marketplace_product_id:
        return False
    Product.objects.filter(pk=obj.marketplace_product_id).update(is_active=False)
    return True


# ---------------------------------------------------------------------------
# Everything at once
# ---------------------------------------------------------------------------

def _unlisted(queryset):
    return queryset.filter(is_active=True).exclude(marketplace_product__is_active=True)


def unlisted_stock(shop):
    from .models import ShopStockItem

    return _unlisted(ShopStockItem.objects.filter(shop=shop))


def unlisted_wholesale(manufacturer):
    from .models import WholesaleProduct

    return _unlisted(WholesaleProduct.objects.filter(manufacturer=manufacturer))


def unlisted_for(seller):
    """The products of this seller that are not on the website yet (their catalog, or their stock for a shop). None if wholesale only."""
    if not seller.retails:
        return unlisted_wholesale(seller).none() if seller.seller_type == "manufacturer" else unlisted_stock(seller).none()
    return unlisted_wholesale(seller) if seller.seller_type == "manufacturer" else unlisted_stock(seller)


def publish_all(seller):
    """List everything not yet listed. Returns (listed, skipped); skipped ones are expired or otherwise cannot be listed."""
    manufacturer = seller.seller_type == "manufacturer"
    listed = skipped = 0
    for obj in unlisted_for(seller).select_related("marketplace_product"):
        try:
            publish_wholesale(obj) if manufacturer else publish_stock_item(obj)
            listed += 1
        except ListingError:
            skipped += 1
    return listed, skipped


# ---------------------------------------------------------------------------
# Keeping the listing in step
# ---------------------------------------------------------------------------

def sync_listing(sender, instance, **kwargs):
    """post_save receiver: when the original's price or quantity changes, so does its listing."""
    if not instance.marketplace_product_id:
        return
    if hasattr(instance, "selling_price"):
        price, stock = instance.selling_price, int(instance.quantity)
    else:
        price, stock = instance.suggested_retail_price or instance.wholesale_price, instance.stock_available
    Product.objects.filter(pk=instance.marketplace_product_id).update(price=price, stock=max(0, stock))


def hide_when_wholesale_only(sender, instance, **kwargs):
    """post_save receiver for InputSeller: someone who does not sell to farmers has nothing on the farmer-facing website."""
    if instance.retails or instance.user_id is None:
        return
    Product.objects.filter(supplier_id=instance.user_id, is_active=True).update(is_active=False)


def hide_agent_listings(supplier, agent):
    """When an agent is removed, the website listings it made from the supplier's products come down."""
    from .models import ShopStockItem

    ids = ShopStockItem.objects.filter(shop=agent, wholesale_product__manufacturer=supplier, marketplace_product__isnull=False).values_list(
        "marketplace_product_id", flat=True
    )
    if not supplier.retails:
        Product.objects.filter(pk__in=list(ids)).update(is_active=False)

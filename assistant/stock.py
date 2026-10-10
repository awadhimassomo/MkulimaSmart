"""
Products a farmer can actually order on Kikapu's WhatsApp for a diagnosis.

The marketplace suggestions (website.Product) have their own ids and are bought on the website. Kikapu's
"Buy inputs" menu sells from input shops' stock (inputs.ShopStockItem), so for Kikapu we also match the
diagnosis against that stock and return items with the SAME ids Kikapu's catalogue uses:
`input-<id>` for the item and `shop-<id>` for the shop (see kikapu_bridge.views.input_json).
Only shops that take Kikapu orders and items that are in stock and in date are returned.
"""
from django.utils import timezone

# Which stock categories address which kind of problem.
CATEGORIES_FOR = {
    "pest": ["pesticides"],
    "disease": ["pesticides"],
    "weed": ["pesticides"],
    "nutrient_deficiency": ["fertilizer", "compost"],
    "soil": ["fertilizer", "compost"],
}


def _number(value):
    value = float(value)
    return int(value) if value == int(value) else value


def orderable_items(diagnosis, limit=3):
    from inputs.models import ShopStockItem

    problem_type = diagnosis.get("problem_type")
    categories = CATEGORIES_FOR.get(problem_type)
    terms = [t for t in diagnosis.get("product_search_terms") or [] if t]
    if not categories and not terms:
        return []
    crop = (diagnosis.get("crop") or "").strip().lower()

    stock = ShopStockItem.objects.filter(
        is_active=True, quantity__gte=1, shop__is_active=True, shop__list_on_kikapu=True, shop__onboarding_completed=True,
    ).select_related("shop", "wholesale_product")
    today = timezone.localdate()

    scored = []
    for item in stock:
        if item.expiry_date and item.expiry_date < today:
            continue
        wholesale = item.wholesale_product
        name = f"{item.name} {item.brand}".lower()
        details = " ".join([
            (wholesale.composition if wholesale else "") or "",
            ", ".join((wholesale.target_crops if wholesale else None) or []),
        ]).lower()
        in_category = bool(categories) and item.category in categories
        term_hits_name = sum(term in name for term in terms)
        term_hits_details = sum(term in details for term in terms)
        if not (in_category or term_hits_name or term_hits_details):
            continue
        score = 3 * term_hits_name + term_hits_details + (2 if in_category else 0)
        score += 2 if crop and (crop in name or crop in details) else 0
        scored.append((score, item.name, item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    results = []
    for _, _, item in scored[:limit]:
        results.append({
            "id": f"input-{item.pk}",
            "shop_id": f"shop-{item.shop_id}",
            "name": item.name,
            "brand": item.brand or None,
            "category": item.category,
            "price": _number(item.selling_price),
            "unit": item.get_unit_display().lower(),
            "shop_name": item.shop.business_name or item.shop.seller_name,
        })
    return results

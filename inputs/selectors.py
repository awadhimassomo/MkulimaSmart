"""
Read-side queries shared by the web views (views.py) and the mobile JSON API (api.py),
so dashboards and filters give the same answers on both.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from operations.models import InputSeller

from .models import FarmerOrder, PurchaseOrder, Sale, SaleItem, ShopStockItem, WholesaleProduct

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=14, decimal_places=2)


def expiring_stock(shop):
    """Active, in-stock items that are expired or expire within the warning window, soonest first."""
    return ShopStockItem.objects.filter(
        shop=shop, is_active=True, quantity__gt=0, expiry_date__isnull=False,
        expiry_date__lte=timezone.localdate() + timedelta(days=ShopStockItem.EXPIRY_WARNING_DAYS),
    ).order_by("expiry_date")


def filter_stock(shop, q="", view=""):
    items = ShopStockItem.objects.filter(shop=shop)
    if q:
        items = items.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(brand__icontains=q) | Q(batch_number__icontains=q))
    if view == "low":
        return items.filter(quantity__lte=F("reorder_level"), is_active=True).order_by("name")
    if view == "expiring":
        return expiring_stock(shop).filter(pk__in=items.values("pk"))
    if view == "inactive":
        items = items.filter(is_active=False)
    return items.order_by("name")


def stock_summary(shop):
    return ShopStockItem.objects.filter(shop=shop, is_active=True).aggregate(
        cost=Sum(ExpressionWrapper(F("quantity") * F("cost_price"), output_field=MONEY)),
        retail=Sum(ExpressionWrapper(F("quantity") * F("selling_price"), output_field=MONEY)),
        count=Count("id"),
    )


def filter_sales(shop, date_from="", date_to="", payment="", q=""):
    sales = Sale.objects.filter(shop=shop).annotate(item_count=Count("items")).order_by("-created_at")
    if date_from:
        sales = sales.filter(created_at__date__gte=date_from)
    if date_to:
        sales = sales.filter(created_at__date__lte=date_to)
    if payment:
        sales = sales.filter(payment_method=payment)
    if q:
        sales = sales.filter(
            Q(receipt_number__icontains=q) | Q(customer_name__icontains=q)
            | Q(customer_phone__icontains=q) | Q(items__product_name__icontains=q)
        ).distinct()
    return sales


def active_catalog():
    return WholesaleProduct.objects.filter(
        is_active=True, manufacturer__is_active=True, manufacturer__seller_type="manufacturer"
    ).select_related("manufacturer").prefetch_related("images")


def filter_catalog(q="", category="", manufacturer="", crop=""):
    products = active_catalog()
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(brand__icontains=q) | Q(composition__icontains=q)
            | Q(description__icontains=q) | Q(manufacturer__business_name__icontains=q)
        )
    if category:
        products = products.filter(category=category)
    if manufacturer:
        products = products.filter(manufacturer_id=manufacturer)
    if crop:
        # target_crops is a JSON list; a text match on its serialised form works on SQLite and Postgres.
        products = products.filter(target_crops__icontains=crop)
    return products.order_by("name")


def catalog_manufacturers():
    return InputSeller.objects.filter(
        seller_type="manufacturer", is_active=True, wholesale_products__is_active=True
    ).distinct().order_by("business_name")


def shop_dashboard_stats(shop):
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    sales = Sale.objects.filter(shop=shop)
    today = sales.filter(created_at__gte=today_start).aggregate(revenue=Sum("total"), count=Count("id"))
    month_sales = sales.filter(created_at__gte=month_start)
    month = month_sales.aggregate(revenue=Sum("total"), count=Count("id"), discount=Sum("discount"))
    month_items = SaleItem.objects.filter(sale__shop=shop, sale__created_at__gte=month_start)
    month_items_totals = month_items.aggregate(
        cost=Sum(ExpressionWrapper(F("cost_price") * F("quantity"), output_field=MONEY)),
        lines=Sum("line_total"),
    )

    stock = ShopStockItem.objects.filter(shop=shop, is_active=True)
    stock_value = stock.aggregate(v=Sum(ExpressionWrapper(F("quantity") * F("cost_price"), output_field=MONEY)))["v"] or ZERO
    low_stock = stock.filter(quantity__lte=F("reorder_level")).order_by("quantity")
    expiring = expiring_stock(shop)

    # Last 7 days of revenue, oldest first.
    week_start = today_start - timedelta(days=6)
    daily = [ZERO] * 7
    for sale in sales.filter(created_at__gte=week_start).only("created_at", "total"):
        index = (timezone.localtime(sale.created_at).date() - week_start.date()).days
        if 0 <= index < 7:
            daily[index] += sale.total
    peak = max(daily) or Decimal("1")
    trend = [
        {
            "date": (week_start + timedelta(days=i)).date(),
            "label": (week_start + timedelta(days=i)).strftime("%a"),
            "value": daily[i],
            "pct": int(daily[i] / peak * 100),
        }
        for i in range(7)
    ]

    return {
        "today_revenue": today["revenue"] or ZERO,
        "today_count": today["count"],
        "month_revenue": month["revenue"] or ZERO,
        "month_count": month["count"],
        "month_profit": (month_items_totals["lines"] or ZERO) - (month["discount"] or ZERO) - (month_items_totals["cost"] or ZERO),
        "stock_value": stock_value,
        "stock_count": stock.count(),
        "low_stock": low_stock,
        "low_stock_count": low_stock.count(),
        "expiring": expiring,
        "expiring_count": expiring.count(),
        "open_orders": PurchaseOrder.objects.filter(shop=shop, status__in=PurchaseOrder.OPEN_STATUSES).select_related("manufacturer"),
        "farmer_orders_open": FarmerOrder.objects.filter(shop=shop, status__in=FarmerOrder.OPEN_STATUSES).prefetch_related("items"),
        "farmer_orders_new_count": FarmerOrder.objects.filter(shop=shop, status="pending").count(),
        "arriving_count": PurchaseOrder.objects.filter(shop=shop, status="dispatched").count(),
        "recent_sales": sales.prefetch_related("items"),
        "top_sellers": (
            month_items.values("product_name")
            .annotate(qty=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-revenue")[:5]
        ),
        "trend": trend,
    }


def manufacturer_dashboard_stats(mfr):
    month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    orders = PurchaseOrder.objects.filter(manufacturer=mfr)
    shipped = orders.filter(status__in=["dispatched", "received"])
    products = WholesaleProduct.objects.filter(manufacturer=mfr)
    return {
        "pending_count": orders.filter(status="pending").count(),
        "to_ship_count": orders.filter(status="confirmed").count(),
        "month_sales": shipped.filter(updated_at__gte=month_start).aggregate(t=Sum("total"))["t"] or ZERO,
        "shop_count": orders.exclude(status="cancelled").values("shop").distinct().count(),
        "product_count": products.count(),
        "low_products": products.filter(is_active=True, stock_available__lt=F("min_order_quantity") * 5).order_by("stock_available"),
        "recent_orders": orders.select_related("shop"),
        "top_products": (
            products.annotate(ordered=Sum("order_items__quantity", filter=~Q(order_items__order__status="cancelled")))
            .filter(ordered__gt=0).order_by("-ordered")[:5]
        ),
    }


def filter_farmer_orders(shop, status=""):
    orders = FarmerOrder.objects.filter(shop=shop).prefetch_related("items")
    if status == "open":
        return orders.filter(status__in=FarmerOrder.OPEN_STATUSES)
    if status:
        return orders.filter(status=status)
    return orders

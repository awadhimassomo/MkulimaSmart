import json
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from community.utils import discussions_for_names
from operations.models import TANZANIA_REGIONS, InputSeller

from . import selectors, services
from .forms import (
    CATEGORY_REQUIRED_FIELDS,
    CROP_SUGGESTIONS,
    ShopStockItemForm,
    StockAdjustmentForm,
    WholesaleProductForm,
)
from .models import (
    FarmerOrder,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    ShopStockItem,
    WholesaleProduct,
    WholesaleProductImage,
)

ZERO = Decimal("0")
ORDER_CART_SESSION_KEY = "inputs_order_cart"
MONEY = DecimalField(max_digits=14, decimal_places=2)


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def _profile_for(user):
    return InputSeller.objects.filter(user=user, onboarding_completed=True).first()


def _role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            profile = _profile_for(request.user)
            if profile is None:
                messages.info(request, "Set up your business profile first.")
                return redirect("marketplace:supplier_onboarding")
            is_manufacturer = profile.seller_type == "manufacturer"
            if (role == "manufacturer") != is_manufacturer:
                return redirect("inputs:home")
            request.seller = profile
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


shop_required = _role_required("shop")
manufacturer_required = _role_required("manufacturer")


@login_required
def home(request):
    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, "Set up your business profile to open your input dashboard.")
        return redirect("marketplace:supplier_onboarding")
    if profile.seller_type == "manufacturer":
        return redirect("inputs:manufacturer_dashboard")
    return redirect("inputs:shop_dashboard")


def _nav_context(request, active):
    context = {"seller": request.seller, "active_nav": active}
    if request.seller.seller_type != "manufacturer":
        context["farmer_orders_badge"] = FarmerOrder.objects.filter(shop=request.seller, status="pending").count()
    return context


def _period_totals(sales_qs):
    return sales_qs.aggregate(revenue=Sum("total"), count=Count("id"))


# ---------------------------------------------------------------------------
# Shop: dashboard
# ---------------------------------------------------------------------------

@shop_required
def shop_dashboard(request):
    stats = selectors.shop_dashboard_stats(request.seller)
    for key in ("low_stock", "expiring", "recent_sales"):
        stats[key] = stats[key][:6]
    stats["open_orders"] = stats["open_orders"][:5]
    stats["farmer_orders_open"] = stats["farmer_orders_open"][:5]
    return render(request, "inputs/shop_dashboard.html", {**_nav_context(request, "dashboard"), **stats})


# ---------------------------------------------------------------------------
# Shop: POS
# ---------------------------------------------------------------------------

@shop_required
def pos(request):
    items = ShopStockItem.objects.filter(shop=request.seller, is_active=True).order_by("name")
    catalog = [
        {
            "id": item.pk,
            "name": item.name,
            "sku": item.sku,
            "category": item.get_category_display(),
            "unit": item.get_unit_display(),
            "price": str(item.selling_price),
            "qty": str(item.quantity),
            "image": item.image.url if item.image else "",
        }
        for item in items
    ]
    context = {
        **_nav_context(request, "pos"),
        "catalog": catalog,
        "payment_choices": Sale.POS_PAYMENT_CHOICES,
    }
    return render(request, "inputs/pos.html", context)


@shop_required
@require_POST
def pos_checkout(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    try:
        sale = services.record_sale(
            request.seller,
            payload.get("lines") or [],
            user=request.user,
            payment_method=payload.get("payment_method", "cash"),
            discount=payload.get("discount") or 0,
            amount_paid=payload.get("amount_paid"),
            customer_name=str(payload.get("customer_name") or ""),
            customer_phone=str(payload.get("customer_phone") or ""),
        )
    except services.StockError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse({
        "ok": True,
        "receipt_number": sale.receipt_number,
        "receipt_url": reverse("inputs:sale_detail", args=[sale.pk]),
    })


# ---------------------------------------------------------------------------
# Shop: sales
# ---------------------------------------------------------------------------

@shop_required
def sale_list(request):
    date_from = request.GET.get("from") or ""
    date_to = request.GET.get("to") or ""
    payment = request.GET.get("payment") or ""
    q = (request.GET.get("q") or "").strip()
    sales = selectors.filter_sales(request.seller, date_from, date_to, payment, q)

    totals = sales.aggregate(revenue=Sum("total"), count=Count("id", distinct=True))
    page = Paginator(sales, 25).get_page(request.GET.get("page"))
    context = {
        **_nav_context(request, "sales"),
        "page_obj": page,
        "totals": totals,
        "payment_choices": Sale.PAYMENT_CHOICES,
        "filters": {"from": date_from, "to": date_to, "payment": payment, "q": q},
    }
    return render(request, "inputs/sale_list.html", context)


@shop_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related("items"), pk=pk, shop=request.seller)
    return render(request, "inputs/sale_detail.html", {**_nav_context(request, "sales"), "sale": sale})


# ---------------------------------------------------------------------------
# Shop: stock
# ---------------------------------------------------------------------------

@shop_required
def stock_list(request):
    q = (request.GET.get("q") or "").strip()
    view = request.GET.get("view") or ""
    context = {
        **_nav_context(request, "stock"),
        "items": selectors.filter_stock(request.seller, q, view),
        "summary": selectors.stock_summary(request.seller),
        "q": q,
        "view": view,
    }
    return render(request, "inputs/stock_list.html", context)


@shop_required
def stock_create(request):
    form = ShopStockItemForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.shop = request.seller
            item.save()
            services.record_opening_stock(item, user=request.user)
        messages.success(request, f"{item.name} added to your stock.")
        return redirect("inputs:stock_list")
    return render(request, "inputs/stock_form.html", {**_nav_context(request, "stock"), "form": form})


@shop_required
def stock_edit(request, pk):
    item = get_object_or_404(ShopStockItem, pk=pk, shop=request.seller)
    form = ShopStockItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{item.name} updated.")
        return redirect("inputs:stock_edit", pk=item.pk)
    context = {
        **_nav_context(request, "stock"),
        "form": form,
        "item": item,
        "adjust_form": StockAdjustmentForm(),
        "movements": item.movements.select_related("created_by")[:30],
    }
    return render(request, "inputs/stock_form.html", context)


@shop_required
@require_POST
def stock_adjust(request, pk):
    item = get_object_or_404(ShopStockItem, pk=pk, shop=request.seller)
    form = StockAdjustmentForm(request.POST)
    if form.is_valid():
        try:
            item = services.adjust_stock(
                request.seller, item.pk, form.cleaned_data["change"], user=request.user, note=form.cleaned_data["note"]
            )
            messages.success(request, f"Stock updated. {item.name} now has {item.quantity}.")
        except services.StockError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Enter a valid quantity change.")
    return redirect("inputs:stock_edit", pk=pk)


# ---------------------------------------------------------------------------
# Shop: ordering from manufacturers
# ---------------------------------------------------------------------------

def _order_cart(request):
    cart = request.session.get(ORDER_CART_SESSION_KEY) or {}
    return {int(k): int(v) for k, v in cart.items() if str(v).isdigit() and int(v) > 0}


def _save_order_cart(request, cart):
    request.session[ORDER_CART_SESSION_KEY] = {str(k): v for k, v in cart.items() if v > 0}


def _active_catalog():
    return selectors.active_catalog()


@shop_required
def catalog(request):
    q = (request.GET.get("q") or "").strip()
    category = request.GET.get("category") or ""
    manufacturer = request.GET.get("manufacturer") or ""
    crop = (request.GET.get("crop") or "").strip()
    # Defaults to the shop's own region so they see what actually suits them first;
    # an explicit ?region= (including empty, "All regions") overrides that.
    region = request.GET.get("region")
    region = region.strip() if region is not None else request.seller.region_or_guess
    products = selectors.filter_catalog(q, category, manufacturer, crop, region)

    stocked = set(
        ShopStockItem.objects.filter(shop=request.seller, wholesale_product__isnull=False).values_list("wholesale_product_id", flat=True)
    )
    page = Paginator(products, 24).get_page(request.GET.get("page"))
    context = {
        **_nav_context(request, "catalog"),
        "page_obj": page,
        "stocked_ids": stocked,
        "cart": _order_cart(request),
        "cart_count": len(_order_cart(request)),
        "categories": InputSeller.PRODUCT_CATEGORY_CHOICES,
        "manufacturers": selectors.catalog_manufacturers(),
        "filters": {"q": q, "category": category, "manufacturer": manufacturer, "crop": crop, "region": region},
        "crop_suggestions": CROP_SUGGESTIONS,
        "region_choices": TANZANIA_REGIONS,
    }
    return render(request, "inputs/catalog.html", context)


@shop_required
def catalog_product(request, pk):
    product = get_object_or_404(_active_catalog(), pk=pk)
    context = {
        **_nav_context(request, "catalog"),
        "product": product,
        "in_cart": _order_cart(request).get(product.pk, 0),
        "cart_count": len(_order_cart(request)),
        "farmer_discussions": discussions_for_names(product.name, product.seed_variety, *product.target_crops),
        "discussion_crop_prefill": product.seed_variety or product.name,
    }
    return render(request, "inputs/catalog_product.html", context)


@shop_required
@require_POST
def order_cart_update(request):
    cart = _order_cart(request)
    try:
        product_id = int(request.POST.get("product"))
        quantity = int(request.POST.get("quantity") or 0)
    except (TypeError, ValueError):
        messages.error(request, "Enter a whole number quantity.")
        return redirect(request.POST.get("next") or "inputs:catalog")

    product = _active_catalog().filter(pk=product_id).first()
    if product is None:
        messages.error(request, "That product is no longer available.")
    elif quantity <= 0:
        cart.pop(product_id, None)
        messages.info(request, f"{product.name} removed from your order.")
    elif quantity < product.min_order_quantity:
        messages.error(request, f"Minimum order for {product.name} is {product.min_order_quantity}.")
    else:
        cart[product_id] = quantity
        messages.success(request, f"{quantity} × {product.name} in your order list.")
    _save_order_cart(request, cart)

    next_url = request.POST.get("next") or ""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("inputs:order_cart")


@shop_required
def order_cart(request):
    cart = _order_cart(request)
    products = _active_catalog().filter(pk__in=cart)
    groups = {}
    for product in products:
        qty = cart[product.pk]
        group = groups.setdefault(product.manufacturer_id, {"manufacturer": product.manufacturer, "lines": [], "total": ZERO})
        line_total = product.wholesale_price * qty
        group["lines"].append({"product": product, "quantity": qty, "line_total": line_total})
        group["total"] += line_total
    # Drop products that vanished from the catalog.
    _save_order_cart(request, {p.pk: cart[p.pk] for p in products})
    context = {**_nav_context(request, "catalog"), "groups": groups.values(), "cart_count": len(cart)}
    return render(request, "inputs/order_cart.html", context)


@shop_required
@require_POST
def order_submit(request, manufacturer_id):
    manufacturer = get_object_or_404(InputSeller, pk=manufacturer_id, seller_type="manufacturer")
    cart = _order_cart(request)
    own_ids = set(WholesaleProduct.objects.filter(pk__in=cart, manufacturer=manufacturer).values_list("pk", flat=True))
    lines = {pid: qty for pid, qty in cart.items() if pid in own_ids}
    try:
        order = services.create_purchase_order(
            request.seller, manufacturer, lines, user=request.user, notes=request.POST.get("notes", "").strip()
        )
    except services.StockError as exc:
        messages.error(request, str(exc))
        return redirect("inputs:order_cart")

    for pid in lines:
        cart.pop(pid, None)
    _save_order_cart(request, cart)
    messages.success(request, f"Order {order.order_number} sent to {manufacturer}.")
    return redirect("inputs:order_detail", pk=order.pk)


@shop_required
def order_list(request):
    orders = PurchaseOrder.objects.filter(shop=request.seller).select_related("manufacturer").annotate(item_count=Count("items")).order_by("-created_at")
    status = request.GET.get("status") or ""
    if status:
        orders = orders.filter(status=status)
    page = Paginator(orders, 20).get_page(request.GET.get("page"))
    context = {
        **_nav_context(request, "orders"),
        "page_obj": page,
        "status": status,
        "status_choices": PurchaseOrder.STATUS_CHOICES,
        "cart_count": len(_order_cart(request)),
    }
    return render(request, "inputs/order_list.html", context)


@shop_required
def order_detail(request, pk):
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("manufacturer").prefetch_related("items"), pk=pk, shop=request.seller
    )
    return render(request, "inputs/order_detail.html", {**_nav_context(request, "orders"), "order": order, "viewer": "shop"})


@shop_required
@require_POST
def order_action(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=request.seller)
    action = request.POST.get("action")
    try:
        if action == "receive":
            services.receive_purchase_order(order, user=request.user)
            messages.success(request, "Order received. Stock has been added to your shop.")
        elif action == "cancel":
            services.shop_cancel_order(order)
            messages.info(request, "Order cancelled.")
        else:
            messages.error(request, "Unknown action.")
    except services.StockError as exc:
        messages.error(request, str(exc))
    return redirect("inputs:order_detail", pk=pk)


# ---------------------------------------------------------------------------
# Manufacturer portal
# ---------------------------------------------------------------------------

@manufacturer_required
def manufacturer_dashboard(request):
    stats = selectors.manufacturer_dashboard_stats(request.seller)
    stats["low_products"] = stats["low_products"][:6]
    stats["recent_orders"] = stats["recent_orders"][:8]
    return render(request, "inputs/manufacturer_dashboard.html", {**_nav_context(request, "dashboard"), **stats})


@manufacturer_required
def manufacturer_products(request):
    products = WholesaleProduct.objects.filter(manufacturer=request.seller).prefetch_related("images").order_by("name")
    return render(request, "inputs/manufacturer_products.html", {**_nav_context(request, "products"), "products": products})


def _save_new_images(product, images):
    has_primary = product.images.filter(is_primary=True).exists()
    for index, image in enumerate(images):
        WholesaleProductImage.objects.create(product=product, image=image, is_primary=not has_primary and index == 0)


@manufacturer_required
def manufacturer_product_form(request, pk=None):
    product = get_object_or_404(WholesaleProduct, pk=pk, manufacturer=request.seller) if pk else None
    form = WholesaleProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            product = form.save(commit=False)
            product.manufacturer = request.seller
            product.save()
            _save_new_images(product, form.cleaned_data.get("new_images") or [])
        messages.success(request, f"{product.name} saved.")
        return redirect("inputs:manufacturer_product_edit", pk=product.pk)
    context = {
        **_nav_context(request, "products"),
        "form": form,
        "product": product,
        "images": product.images.all() if product else [],
        "crop_suggestions": CROP_SUGGESTIONS,
        "category_rules": CATEGORY_REQUIRED_FIELDS,
    }
    return render(request, "inputs/manufacturer_product_form.html", context)


@manufacturer_required
@require_POST
def manufacturer_image_action(request, pk):
    image = get_object_or_404(WholesaleProductImage.objects.select_related("product"), pk=pk, product__manufacturer=request.seller)
    product = image.product
    if request.POST.get("action") == "primary":
        with transaction.atomic():
            product.images.update(is_primary=False)
            image.is_primary = True
            image.save(update_fields=["is_primary"])
        messages.success(request, "Cover photo updated.")
    elif request.POST.get("action") == "delete":
        if product.images.count() <= 1:
            messages.error(request, "Every product needs at least one photo. Upload another before removing this one.")
            return redirect("inputs:manufacturer_product_edit", pk=product.pk)
        was_primary = image.is_primary
        image.image.delete(save=False)
        image.delete()
        if was_primary:
            replacement = product.images.first()
            if replacement:
                replacement.is_primary = True
                replacement.save(update_fields=["is_primary"])
        messages.info(request, "Photo removed.")
    return redirect("inputs:manufacturer_product_edit", pk=product.pk)


@manufacturer_required
def manufacturer_orders(request):
    orders = PurchaseOrder.objects.filter(manufacturer=request.seller).select_related("shop").annotate(item_count=Count("items")).order_by("-created_at")
    status = request.GET.get("status") or ""
    if status:
        orders = orders.filter(status=status)
    page = Paginator(orders, 20).get_page(request.GET.get("page"))
    context = {
        **_nav_context(request, "orders"),
        "page_obj": page,
        "status": status,
        "status_choices": PurchaseOrder.STATUS_CHOICES,
    }
    return render(request, "inputs/order_list.html", context)


@manufacturer_required
def manufacturer_order_detail(request, pk):
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("shop").prefetch_related(
            Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("wholesale_product"))
        ),
        pk=pk,
        manufacturer=request.seller,
    )
    if request.method == "POST":
        try:
            services.manufacturer_update_order(order, request.POST.get("status"), note=request.POST.get("note", "").strip())
            messages.success(request, "Order updated.")
        except services.StockError as exc:
            messages.error(request, str(exc))
        return redirect("inputs:manufacturer_order_detail", pk=pk)
    return render(request, "inputs/order_detail.html", {**_nav_context(request, "orders"), "order": order, "viewer": "manufacturer"})


# ---------------------------------------------------------------------------
# Shop: farmer orders (from Kikapu WhatsApp)
# ---------------------------------------------------------------------------

@shop_required
def farmer_order_list(request):
    status = request.GET.get("status", "open")
    orders = selectors.filter_farmer_orders(request.seller, status)
    page = Paginator(orders, 20).get_page(request.GET.get("page"))
    context = {
        **_nav_context(request, "farmer_orders"),
        "page_obj": page,
        "status": status,
        "status_choices": FarmerOrder.STATUS_CHOICES,
    }
    return render(request, "inputs/farmer_order_list.html", context)


@shop_required
def farmer_order_detail(request, pk):
    order = get_object_or_404(FarmerOrder.objects.prefetch_related("items"), pk=pk, shop=request.seller)
    if request.method == "POST":
        new_status = request.POST.get("status", "")
        try:
            services.update_farmer_order_status(order, new_status, user=request.user, note=request.POST.get("note", ""))
            label = dict(FarmerOrder.STATUS_CHOICES).get(new_status, new_status).lower()
            messages.success(request, f"Order marked {label}. The farmer will get a WhatsApp update.")
        except services.StockError as exc:
            messages.error(request, str(exc))
        return redirect("inputs:farmer_order_detail", pk=pk)

    last_webhook = order.kikapu_webhooks.order_by("-created_at").first() if hasattr(order, "kikapu_webhooks") else None
    context = {**_nav_context(request, "farmer_orders"), "order": order, "last_webhook": last_webhook}
    return render(request, "inputs/farmer_order_detail.html", context)

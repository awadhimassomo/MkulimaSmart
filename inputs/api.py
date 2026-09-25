"""
JSON API for the Flutter app, mounted at /api/inputs/.

Auth: the same JWT the app gets from /api/auth/login/ (Authorization: Bearer <access_token>).
Validation: every create/update runs the same Django form as the web pages (forms.py),
so the rules in docs/inputs/product-forms.md apply to both.
Errors: {"success": false, "message": "...", "errors": {"field": ["message", ...]}}.
"""
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.forms.models import model_to_dict
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from django.utils.datastructures import MultiValueDict
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from marketplace.forms import SupplierOnboardingForm
from operations.models import TANZANIA_REGIONS, InputSeller

from . import selectors, services
from .forms import (
    ALWAYS_REQUIRED_FIELDS,
    CATEGORY_REQUIRED_FIELDS,
    CROP_SUGGESTIONS,
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_UPLOAD,
    MultipleImageField,
    ShopStockItemForm,
    StockAdjustmentForm,
    WholesaleProductForm,
)
from .models import FarmerOrder, PurchaseOrder, Sale, ShopStockItem, WholesaleProduct, WholesaleProductImage
from .serializers import (
    FarmerOrderSerializer,
    PurchaseOrderListSerializer,
    PurchaseOrderSerializer,
    SaleListSerializer,
    SaleSerializer,
    SellerBriefSerializer,
    SellerSerializer,
    StockItemSerializer,
    StockMovementSerializer,
    WholesaleProductSerializer,
)

# The web form calls the photo field "new_images"; the API calls it "images".
API_FIELD_NAMES = {"new_images": "images", "__all__": "non_field_errors"}
LIST_FIELDS = {"target_crops", "products_offered", "suitable_regions", "soil_type"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class InputsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"  # e.g. ?page_size=500 to load all stock into the POS
    max_page_size = 500


def error(message, errors=None, http_status=status.HTTP_400_BAD_REQUEST, code=None):
    body = {"success": False, "message": message}
    if errors:
        body["errors"] = errors
    if code:
        body["code"] = code
    return Response(body, status=http_status)


def form_error(form):
    errors = {
        API_FIELD_NAMES.get(field, field): [e["message"] for e in messages]
        for field, messages in form.errors.get_json_data().items()
    }
    return error("Please correct the highlighted fields.", errors)


def request_values(request):
    """request.data as a plain dict; list fields keep all values from multipart forms."""
    data = request.data
    if isinstance(data, QueryDict):
        return {key: (data.getlist(key) if key in LIST_FIELDS else data.get(key)) for key in data.keys()}
    return dict(data)


def form_data(request, form_class, instance=None, defaults=None):
    """
    Data for a form: on update (PATCH) start from the saved values so only sent fields change;
    on create, start from sensible defaults (the web form's checkboxes are pre-ticked).
    """
    fields = [f for f in form_class._meta.fields if f not in ("image", "certificate_file")]
    base = model_to_dict(instance, fields=fields) if instance else dict(defaults or {})
    base = {k: v for k, v in base.items() if v is not None}
    base.update(request_values(request))
    if base.pop("remove_image", False) in (True, "true", "1", "on"):
        base["image-clear"] = "on"
    return base


def form_files(request, rename=None):
    files = MultiValueDict()
    for key in request.FILES:
        files.setlist((rename or {}).get(key, key), request.FILES.getlist(key))
    return files


def paginated(request, view, queryset, serializer_class, context=None, extra=None):
    paginator = InputsPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    data = serializer_class(page, many=True, context={"request": request, **(context or {})}).data
    response = paginator.get_paginated_response(data)
    if extra:
        response.data.update(extra)
    return response


def profile_for(user):
    return InputSeller.objects.filter(user=user, onboarding_completed=True).first()


class HasBusinessProfile(BasePermission):
    role = None
    message = "Complete your business profile first (POST /api/inputs/profile/)."

    def has_permission(self, request, view):
        profile = profile_for(request.user)
        if profile is None:
            raise PermissionDenied({"success": False, "code": "profile_required", "message": self.message})
        is_manufacturer = profile.seller_type == "manufacturer"
        if self.role == "manufacturer" and not is_manufacturer:
            raise PermissionDenied({"success": False, "code": "wrong_role", "message": "Only manufacturers can use this endpoint."})
        if self.role == "shop" and is_manufacturer:
            raise PermissionDenied({"success": False, "code": "wrong_role", "message": "Only input shops can use this endpoint."})
        request.seller = profile
        return True


class IsShop(HasBusinessProfile):
    role = "shop"


class IsManufacturer(HasBusinessProfile):
    role = "manufacturer"


class ShopAPIView(APIView):
    permission_classes = [IsAuthenticated, IsShop]


class ManufacturerAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManufacturer]


def choices(pairs):
    return [{"value": value, "label": str(label)} for value, label in pairs]


# ---------------------------------------------------------------------------
# Shared: options and business profile
# ---------------------------------------------------------------------------

class OptionsView(APIView):
    """Every dropdown value and form rule, so the app doesn't hard-code them."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "seller_types": choices(InputSeller.SELLER_TYPE_CHOICES),
            "categories": choices(InputSeller.PRODUCT_CATEGORY_CHOICES),
            "units": choices(WholesaleProduct.UNIT_CHOICES),
            "regulators": choices(WholesaleProduct.REGULATOR_CHOICES),
            "category_regulator": WholesaleProduct.CATEGORY_REGULATOR,
            "toxicity_classes": choices(WholesaleProduct.TOXICITY_CHOICES),
            "regions": choices(TANZANIA_REGIONS),
            "soil_types": choices(WholesaleProduct.SOIL_TYPE_CHOICES),
            "payment_methods": choices(Sale.POS_PAYMENT_CHOICES),
            "order_statuses": choices(PurchaseOrder.STATUS_CHOICES),
            "farmer_order_statuses": choices(FarmerOrder.STATUS_CHOICES),
            "crop_suggestions": CROP_SUGGESTIONS,
            "product_form": {
                "always_required": ALWAYS_REQUIRED_FIELDS + ["images"],
                "required_by_category": CATEGORY_REQUIRED_FIELDS,
                "max_image_bytes": MAX_IMAGE_BYTES,
                "max_images_per_upload": MAX_IMAGES_PER_UPLOAD,
                "image_types": ["jpg", "jpeg", "png", "webp"],
            },
            "stock_form": {
                "expiry_required_categories": ["seeds", "pesticides"],
                "expiry_warning_days": ShopStockItem.EXPIRY_WARNING_DAYS,
            },
        })


class ProfileView(APIView):
    """GET the business profile; POST/PATCH to create or update it (multipart if uploading a certificate)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = InputSeller.objects.filter(user=request.user).first()
        if profile is None or not profile.onboarding_completed:
            return Response({"profile": None, "role": None})
        data = SellerSerializer(profile, context={"request": request}).data
        return Response({"profile": data, "role": data["role"]})

    def post(self, request):
        profile = InputSeller.get_or_create_for_user(request.user)
        form = SupplierOnboardingForm(
            form_data(
                request, SupplierOnboardingForm,
                instance=profile if profile.onboarding_completed else None,
                defaults={"list_on_kikapu": True},
            ),
            form_files(request),
            instance=profile,
        )
        if not form.is_valid():
            return form_error(form)
        with transaction.atomic():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.seller_name = request.user.get_full_name() or request.user.phone_number
            profile.phone_number = request.user.phone_number
            profile.onboarding_completed = True
            profile.is_active = True
            profile.save()
            if not request.user.is_supplier:
                request.user.is_supplier = True
                request.user.save(update_fields=["is_supplier"])
        data = SellerSerializer(profile, context={"request": request}).data
        return Response({"success": True, "profile": data, "role": data["role"]})

    patch = post


# ---------------------------------------------------------------------------
# Shop: dashboard, stock, POS / sales
# ---------------------------------------------------------------------------

class ShopDashboardView(ShopAPIView):
    def get(self, request):
        stats = selectors.shop_dashboard_stats(request.seller)
        ctx = {"request": request}
        return Response({
            "shop": SellerBriefSerializer(request.seller).data,
            "today": {"revenue": stats["today_revenue"], "sales": stats["today_count"]},
            "month": {"revenue": stats["month_revenue"], "sales": stats["month_count"], "gross_profit": stats["month_profit"]},
            "stock": {
                "value_at_cost": stats["stock_value"], "products": stats["stock_count"],
                "low_stock_count": stats["low_stock_count"], "expiring_count": stats["expiring_count"],
            },
            "orders": {
                "arriving_count": stats["arriving_count"],
                "open": PurchaseOrderListSerializer(
                    stats["open_orders"].annotate(item_count=Count("items")).order_by("-created_at")[:5], many=True, context={**ctx, "viewer": "shop"}).data,
            },
            "farmer_orders": {
                "new_count": stats["farmer_orders_new_count"],
                "open": FarmerOrderSerializer(stats["farmer_orders_open"][:5], many=True, context=ctx).data,
            },
            "low_stock": StockItemSerializer(stats["low_stock"][:6], many=True, context=ctx).data,
            "expiring": StockItemSerializer(stats["expiring"][:6], many=True, context=ctx).data,
            "recent_sales": SaleListSerializer(
                selectors.filter_sales(request.seller)[:6], many=True, context=ctx
            ).data,
            "top_sellers": [
                {"product_name": row["product_name"], "quantity": row["qty"], "revenue": row["revenue"]}
                for row in stats["top_sellers"]
            ],
            "last_7_days": [{"date": d["date"], "label": d["label"], "revenue": d["value"]} for d in stats["trend"]],
        })


class StockListView(ShopAPIView):
    """GET ?q=&view=low|expiring|inactive&page_size= · POST create (JSON, or multipart with `image`)."""

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        view = request.query_params.get("view") or ""
        summary = selectors.stock_summary(request.seller)
        return paginated(
            request, self, selectors.filter_stock(request.seller, q, view), StockItemSerializer,
            extra={"summary": {"products": summary["count"], "value_at_cost": summary["cost"] or 0, "value_at_price": summary["retail"] or 0}},
        )

    def post(self, request):
        form = ShopStockItemForm(form_data(request, ShopStockItemForm, defaults={"is_active": True}), form_files(request))
        if not form.is_valid():
            return form_error(form)
        with transaction.atomic():
            item = form.save(commit=False)
            item.shop = request.seller
            item.save()
            services.record_opening_stock(item, user=request.user)
        return Response(StockItemSerializer(item, context={"request": request}).data, status=status.HTTP_201_CREATED)


class StockDetailView(ShopAPIView):
    """GET · PATCH (send only the fields to change; `quantity` is ignored, use /adjust/; `remove_image: true` clears the photo)."""

    def get(self, request, pk):
        item = get_object_or_404(ShopStockItem, pk=pk, shop=request.seller)
        return Response(StockItemSerializer(item, context={"request": request}).data)

    def patch(self, request, pk):
        item = get_object_or_404(ShopStockItem, pk=pk, shop=request.seller)
        form = ShopStockItemForm(form_data(request, ShopStockItemForm, instance=item), form_files(request), instance=item)
        if not form.is_valid():
            return form_error(form)
        item = form.save()
        return Response(StockItemSerializer(item, context={"request": request}).data)


class StockAdjustView(ShopAPIView):
    """POST {"change": -2, "note": "Damaged"}"""

    def post(self, request, pk):
        item = get_object_or_404(ShopStockItem, pk=pk, shop=request.seller)
        form = StockAdjustmentForm(request_values(request))
        if not form.is_valid():
            return form_error(form)
        try:
            item = services.adjust_stock(request.seller, item.pk, form.cleaned_data["change"], user=request.user, note=form.cleaned_data["note"])
        except services.StockError as exc:
            return error(str(exc), {"change": [str(exc)]})
        return Response(StockItemSerializer(item, context={"request": request}).data)


class StockMovementsView(ShopAPIView):
    def get(self, request, pk):
        item = get_object_or_404(ShopStockItem, pk=pk, shop=request.seller)
        return paginated(request, self, item.movements.all(), StockMovementSerializer)


class SaleListView(ShopAPIView):
    """
    GET ?from=YYYY-MM-DD&to=&payment=&q= · POST = POS checkout:
    {"lines": [{"stock_item": 5, "quantity": 2}], "payment_method": "cash", "discount": 0,
     "amount_paid": 30000, "customer_name": "", "customer_phone": ""}
    """

    def get(self, request):
        p = request.query_params
        sales = selectors.filter_sales(request.seller, p.get("from") or "", p.get("to") or "", p.get("payment") or "", (p.get("q") or "").strip())
        totals = sales.order_by().aggregate(revenue=Sum("total"), count=Count("id", distinct=True))
        return paginated(request, self, sales, SaleListSerializer, extra={"totals": {"revenue": totals["revenue"] or 0, "sales": totals["count"]}})

    def post(self, request):
        data = request.data
        try:
            sale = services.record_sale(
                request.seller,
                data.get("lines") or [],
                user=request.user,
                payment_method=data.get("payment_method", "cash"),
                discount=data.get("discount") or 0,
                amount_paid=data.get("amount_paid"),
                customer_name=str(data.get("customer_name") or ""),
                customer_phone=str(data.get("customer_phone") or ""),
            )
        except services.StockError as exc:
            return error(str(exc))
        sale = Sale.objects.prefetch_related("items").get(pk=sale.pk)
        return Response(SaleSerializer(sale, context={"request": request}).data, status=status.HTTP_201_CREATED)


class SaleDetailView(ShopAPIView):
    def get(self, request, pk):
        sale = get_object_or_404(Sale.objects.prefetch_related("items"), pk=pk, shop=request.seller)
        return Response(SaleSerializer(sale, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Shop: catalog and purchase orders
# ---------------------------------------------------------------------------

def _stocked_ids(shop):
    return set(ShopStockItem.objects.filter(shop=shop, wholesale_product__isnull=False).values_list("wholesale_product_id", flat=True))


class CatalogView(ShopAPIView):
    """GET ?q=&category=&manufacturer=<id>&crop=&region= (region also matches products with no region restriction)"""

    def get(self, request):
        p = request.query_params
        products = selectors.filter_catalog(
            (p.get("q") or "").strip(), p.get("category") or "", p.get("manufacturer") or "",
            (p.get("crop") or "").strip(), (p.get("region") or "").strip(),
        )
        return paginated(request, self, products, WholesaleProductSerializer, context={"stocked_ids": _stocked_ids(request.seller)})


class CatalogDetailView(ShopAPIView):
    def get(self, request, pk):
        product = get_object_or_404(selectors.active_catalog(), pk=pk)
        ctx = {"request": request, "stocked_ids": _stocked_ids(request.seller)}
        return Response(WholesaleProductSerializer(product, context=ctx).data)


class CatalogManufacturersView(ShopAPIView):
    def get(self, request):
        return Response(SellerBriefSerializer(selectors.catalog_manufacturers(), many=True).data)


def _shop_orders(shop):
    return PurchaseOrder.objects.filter(shop=shop).select_related("shop", "manufacturer")


class ShopOrderListView(ShopAPIView):
    """
    GET ?status= · POST place orders:
    {"items": [{"product": 3, "quantity": 10}, ...], "notes": "Deliver Monday"}
    Items may come from several manufacturers; one order is created per manufacturer.
    """

    def get(self, request):
        orders = _shop_orders(request.seller).annotate(item_count=Count("items")).order_by("-created_at")
        if request.query_params.get("status"):
            orders = orders.filter(status=request.query_params["status"])
        return paginated(request, self, orders, PurchaseOrderListSerializer, context={"viewer": "shop"})

    def post(self, request):
        items = request.data.get("items") or []
        if not isinstance(items, list) or not items:
            return error("Add at least one product to the order.", {"items": ["This field is required."]})

        quantities = {}
        for index, line in enumerate(items):
            try:
                product_id, quantity = int(line["product"]), int(line["quantity"])
            except (KeyError, TypeError, ValueError):
                return error("Each item needs a product id and a whole-number quantity.", {"items": [f"Item {index + 1} is invalid."]})
            if quantity < 1:
                return error("Quantities must be at least 1.", {"items": [f"Item {index + 1} has quantity {quantity}."]})
            quantities[product_id] = quantities.get(product_id, 0) + quantity

        products = {p.pk: p for p in selectors.active_catalog().filter(pk__in=quantities)}
        missing = sorted(set(quantities) - set(products))
        if missing:
            return error("Some products are no longer available.", {"items": [f"Product {pid} is not available." for pid in missing]})

        by_manufacturer = defaultdict(dict)
        for pid, qty in quantities.items():
            by_manufacturer[products[pid].manufacturer][pid] = qty

        notes = str(request.data.get("notes") or "").strip()
        try:
            with transaction.atomic():
                orders = [
                    services.create_purchase_order(request.seller, manufacturer, lines, user=request.user, notes=notes)
                    for manufacturer, lines in by_manufacturer.items()
                ]
        except services.StockError as exc:
            return error(str(exc))

        orders = _shop_orders(request.seller).prefetch_related("items").filter(pk__in=[o.pk for o in orders])
        data = PurchaseOrderSerializer(orders, many=True, context={"request": request, "viewer": "shop"}).data
        return Response({"success": True, "orders": data}, status=status.HTTP_201_CREATED)


class ShopOrderDetailView(ShopAPIView):
    def get(self, request, pk):
        order = get_object_or_404(_shop_orders(request.seller).prefetch_related("items"), pk=pk)
        return Response(PurchaseOrderSerializer(order, context={"request": request, "viewer": "shop"}).data)


class ShopOrderActionView(ShopAPIView):
    """POST /receive/ or /cancel/"""

    action = None

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk, shop=request.seller)
        try:
            if self.action == "receive":
                services.receive_purchase_order(order, user=request.user)
            else:
                services.shop_cancel_order(order)
        except services.StockError as exc:
            return error(str(exc))
        order = _shop_orders(request.seller).prefetch_related("items").get(pk=pk)
        return Response(PurchaseOrderSerializer(order, context={"request": request, "viewer": "shop"}).data)


# ---------------------------------------------------------------------------
# Manufacturer
# ---------------------------------------------------------------------------

class ManufacturerDashboardView(ManufacturerAPIView):
    def get(self, request):
        stats = selectors.manufacturer_dashboard_stats(request.seller)
        ctx = {"request": request, "viewer": "manufacturer"}
        return Response({
            "manufacturer": SellerBriefSerializer(request.seller).data,
            "pending_orders": stats["pending_count"],
            "to_dispatch": stats["to_ship_count"],
            "shipped_this_month": stats["month_sales"],
            "shops_buying": stats["shop_count"],
            "products_listed": stats["product_count"],
            "recent_orders": PurchaseOrderListSerializer(
                stats["recent_orders"].annotate(item_count=Count("items")).order_by("-created_at")[:8], many=True, context=ctx
            ).data,
            "low_stock_products": [
                {"id": p.pk, "name": p.name, "stock_available": p.stock_available} for p in stats["low_products"][:6]
            ],
            "top_products": [{"id": p.pk, "name": p.name, "ordered": p.ordered} for p in stats["top_products"]],
        })


def _own_products(mfr):
    return WholesaleProduct.objects.filter(manufacturer=mfr).select_related("manufacturer").prefetch_related("images")


class ManufacturerProductListView(ManufacturerAPIView):
    """GET ?q=&active=true|false · POST create: multipart/form-data with fields + one or more `images` files."""

    def get(self, request):
        products = _own_products(request.seller).order_by("name")
        q = (request.query_params.get("q") or "").strip()
        if q:
            products = products.filter(name__icontains=q)
        active = request.query_params.get("active")
        if active in ("true", "false"):
            products = products.filter(is_active=active == "true")
        return paginated(request, self, products, WholesaleProductSerializer)

    def post(self, request):
        form = WholesaleProductForm(
            form_data(request, WholesaleProductForm, defaults={"is_active": True, "min_order_quantity": 1}),
            form_files(request, rename={"images": "new_images"}),
        )
        if not form.is_valid():
            return form_error(form)
        with transaction.atomic():
            product = form.save(commit=False)
            product.manufacturer = request.seller
            product.save()
            _save_images(product, form.cleaned_data.get("new_images") or [])
        return Response(
            WholesaleProductSerializer(_own_products(request.seller).get(pk=product.pk), context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


def _save_images(product, images):
    has_primary = product.images.filter(is_primary=True).exists()
    for index, image in enumerate(images):
        WholesaleProductImage.objects.create(product=product, image=image, is_primary=not has_primary and index == 0)


class ManufacturerProductDetailView(ManufacturerAPIView):
    """GET · PATCH (send only fields to change; may include new `images` files)."""

    def get(self, request, pk):
        product = get_object_or_404(_own_products(request.seller), pk=pk)
        return Response(WholesaleProductSerializer(product, context={"request": request}).data)

    def patch(self, request, pk):
        product = get_object_or_404(WholesaleProduct, pk=pk, manufacturer=request.seller)
        form = WholesaleProductForm(
            form_data(request, WholesaleProductForm, instance=product),
            form_files(request, rename={"images": "new_images"}),
            instance=product,
        )
        if not form.is_valid():
            return form_error(form)
        with transaction.atomic():
            product = form.save()
            _save_images(product, form.cleaned_data.get("new_images") or [])
        return Response(WholesaleProductSerializer(_own_products(request.seller).get(pk=pk), context={"request": request}).data)


class ManufacturerProductImagesView(ManufacturerAPIView):
    """POST multipart with one or more `images` files to add photos."""

    def post(self, request, pk):
        product = get_object_or_404(WholesaleProduct, pk=pk, manufacturer=request.seller)
        field = MultipleImageField(required=True)
        try:
            images = field.clean(request.FILES.getlist("images"))
        except ValidationError as exc:
            return error("Could not upload the photos.", {"images": exc.messages})
        _save_images(product, images)
        return Response(WholesaleProductSerializer(_own_products(request.seller).get(pk=pk), context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


class ManufacturerImageView(ManufacturerAPIView):
    """DELETE a photo (refused for the last one) · POST /set-primary/ to make it the cover."""

    def _image(self, request, pk):
        return get_object_or_404(WholesaleProductImage.objects.select_related("product"), pk=pk, product__manufacturer=request.seller)

    def delete(self, request, pk):
        image = self._image(request, pk)
        product = image.product
        if product.images.count() <= 1:
            return error("Every product needs at least one photo. Upload another before removing this one.", code="last_photo")
        with transaction.atomic():
            was_primary = image.is_primary
            image.image.delete(save=False)
            image.delete()
            if was_primary:
                replacement = product.images.first()
                if replacement:
                    replacement.is_primary = True
                    replacement.save(update_fields=["is_primary"])
        return Response(WholesaleProductSerializer(_own_products(request.seller).get(pk=product.pk), context={"request": request}).data)


class ManufacturerImagePrimaryView(ManufacturerImageView):
    def post(self, request, pk):
        image = self._image(request, pk)
        with transaction.atomic():
            image.product.images.update(is_primary=False)
            image.is_primary = True
            image.save(update_fields=["is_primary"])
        return Response(WholesaleProductSerializer(_own_products(request.seller).get(pk=image.product_id), context={"request": request}).data)


def _manufacturer_orders(mfr):
    return PurchaseOrder.objects.filter(manufacturer=mfr).select_related("shop", "manufacturer")


class ManufacturerOrderListView(ManufacturerAPIView):
    def get(self, request):
        orders = _manufacturer_orders(request.seller).annotate(item_count=Count("items")).order_by("-created_at")
        if request.query_params.get("status"):
            orders = orders.filter(status=request.query_params["status"])
        return paginated(request, self, orders, PurchaseOrderListSerializer, context={"viewer": "manufacturer"})


class ManufacturerOrderDetailView(ManufacturerAPIView):
    def get(self, request, pk):
        order = get_object_or_404(_manufacturer_orders(request.seller).prefetch_related("items"), pk=pk)
        return Response(PurchaseOrderSerializer(order, context={"request": request, "viewer": "manufacturer"}).data)


class ManufacturerOrderStatusView(ManufacturerAPIView):
    """POST {"status": "confirmed" | "dispatched" | "cancelled", "note": "..."}"""

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk, manufacturer=request.seller)
        new_status = request.data.get("status")
        if new_status not in services.MANUFACTURER_TRANSITIONS:
            return error("Status must be confirmed, dispatched or cancelled.", {"status": ["Invalid status."]})
        try:
            services.manufacturer_update_order(order, new_status, note=str(request.data.get("note") or "").strip())
        except services.StockError as exc:
            return error(str(exc))
        order = _manufacturer_orders(request.seller).prefetch_related("items").get(pk=pk)
        return Response(PurchaseOrderSerializer(order, context={"request": request, "viewer": "manufacturer"}).data)



# ---------------------------------------------------------------------------
# Shop: farmer orders (from Kikapu WhatsApp)
# ---------------------------------------------------------------------------

class FarmerOrderListView(ShopAPIView):
    """GET ?status=open (default: pending, confirmed, dispatched) | pending | confirmed | dispatched | delivered | cancelled | all"""

    def get(self, request):
        status_filter = request.query_params.get("status", "open")
        orders = selectors.filter_farmer_orders(request.seller, "" if status_filter == "all" else status_filter)
        return paginated(request, self, orders, FarmerOrderSerializer)


class FarmerOrderDetailView(ShopAPIView):
    def get(self, request, pk):
        order = get_object_or_404(FarmerOrder.objects.prefetch_related("items"), pk=pk, shop=request.seller)
        return Response(FarmerOrderSerializer(order, context={"request": request}).data)


class FarmerOrderStatusView(ShopAPIView):
    """POST {"status": "confirmed" | "dispatched" | "delivered" | "cancelled", "note": "message for the farmer"}"""

    def post(self, request, pk):
        order = get_object_or_404(FarmerOrder, pk=pk, shop=request.seller)
        try:
            services.update_farmer_order_status(
                order, str(request.data.get("status") or ""), user=request.user, note=str(request.data.get("note") or "")
            )
        except services.StockError as exc:
            return error(str(exc), {"status": [str(exc)]})
        order = FarmerOrder.objects.prefetch_related("items").get(pk=pk)
        return Response(FarmerOrderSerializer(order, context={"request": request}).data)

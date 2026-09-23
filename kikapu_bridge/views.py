"""
Kikapu ⇄ Mkulima Smart inputs bridge (Mkulima Smart's side), mounted at /api/kikapu-bridge/.

    GET  shops/                 §4  shops that sell inputs
    GET  inputs/                §5  shop stock (what farmers can buy)
    GET  inputs/prices/         §5  light price/stock poll
    POST orders/                §6  farmer order from WhatsApp
    GET  orders/<id>/               order status (fallback if a webhook was missed)

Auth: Authorization: Bearer <token issued with `manage.py issue_kikapu_token`>.
"""
import re
from datetime import datetime, time, timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from inputs import services
from inputs.models import FarmerOrder, ShopStockItem
from operations.models import InputSeller

from .auth import IsBridgePartner, PartnerTokenAuthentication

# Our categories -> the vocabulary Kikapu's chat understands.
KIKAPU_CATEGORY = {
    "seeds": "seeds",
    "seedlings": "seeds",
    "fertilizer": "fertilizer",
    "compost": "fertilizer",
    "pesticides": "pesticide",
    "tools": "equipment",
    "feed": "other",
    "other": "other",
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def iso(dt):
    return dt.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def e164(phone):
    """Tanzanian numbers to E.164: 0712345678 / 255712345678 / +255 712 345 678 -> +255712345678."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if digits.startswith("0") and len(digits) == 10:
        digits = "255" + digits[1:]
    elif len(digits) == 9:
        digits = "255" + digits
    return "+" + digits if len(digits) >= 11 else None


def parse_prefixed_id(value, prefix):
    """"shop-12" or "12" -> 12; anything else -> None."""
    text = str(value or "").strip()
    if text.startswith(prefix + "-"):
        text = text[len(prefix) + 1:]
    return int(text) if text.isdigit() else None


def public_media_url(request, file_field):
    if not file_field:
        return None
    base = (getattr(settings, "KIKAPU_BRIDGE_PUBLIC_BASE_URL", "") or getattr(settings, "SITE_BASE_URL", "")).rstrip("/")
    return f"{base}{file_field.url}" if base else request.build_absolute_uri(file_field.url)


def number(value):
    if value is None:
        return None
    value = Decimal(value)
    return int(value) if value == value.to_integral_value() else float(value)


def shop_is_listed(shop):
    return bool(shop.is_active and shop.list_on_kikapu and shop.onboarding_completed)


def shop_json(shop):
    return {
        "id": f"shop-{shop.pk}",
        "name": shop.business_name or shop.seller_name,
        "region": shop.region_or_guess,
        "district": shop.district or None,
        "latitude": number(shop.latitude),
        "longitude": number(shop.longitude),
        "phone_number": e164(shop.phone_number),
        "is_active": shop_is_listed(shop),
        "updated_at": iso(shop.updated_at),
    }


def input_is_active(item):
    return bool(item.is_active and shop_is_listed(item.shop))


def input_in_stock(item):
    return bool(input_is_active(item) and item.quantity >= 1 and not item.is_expired)


def input_unit(item):
    unit = item.get_unit_display().lower()
    pack = item.wholesale_product.pack_size if item.wholesale_product_id and item.wholesale_product else ""
    return f"{pack} {unit}".strip() if pack else unit


def input_json(request, item):
    return {
        "id": f"input-{item.pk}",
        "shop_id": f"shop-{item.shop_id}",
        "name": item.name,
        "brand": item.brand or None,
        "category": KIKAPU_CATEGORY.get(item.category, "other"),
        "mkulima_category": item.category,
        "unit": input_unit(item),
        "price": number(item.selling_price),
        "stock_quantity": int(item.quantity),
        "in_stock": input_in_stock(item),
        "description": _short_description(item),
        "image_url": public_media_url(request, item.image),
        "is_active": input_is_active(item),
        "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
        "updated_at": iso(item.updated_at),
    }


def _short_description(item):
    product = item.wholesale_product if item.wholesale_product_id else None
    parts = [item.brand, product.composition if product else "", product.usage_instructions if product else ""]
    text = " · ".join(p.strip() for p in parts if p and p.strip())
    return text[:280] or None


def price_json(item):
    return {
        "id": f"input-{item.pk}",
        "price": number(item.selling_price),
        "stock_quantity": int(item.quantity),
        "in_stock": input_in_stock(item),
        "updated_at": iso(item.updated_at),
    }


def order_json(order):
    return {
        "success": True,
        "kikapu_order_id": order.external_order_id,
        "mkulima_order_id": order.order_number,
        "shop_id": f"shop-{order.shop_id}",
        "status": order.status,
        "total_price": number(order.total),
        "note": order.shop_note,
        "items": [
            {
                "input_id": f"input-{line.stock_item_id}" if line.stock_item_id else None,
                "name": line.product_name,
                "quantity": number(line.quantity),
                "unit_price": number(line.unit_price),
                "line_total": number(line.line_total),
            }
            for line in order.items.all()
        ],
        "created_at": iso(order.created_at),
        "updated_at": iso(order.updated_at),
    }


def fail(http_status, code, message, errors=None):
    body = {"success": False, "code": code, "reason": message, "message": message}
    if errors:
        body["errors"] = errors
    return Response(body, status=http_status)


def parse_updated_since(request):
    """Returns (datetime | None, error Response | None)."""
    raw = (request.query_params.get("updated_since") or "").strip()
    if not raw:
        return None, None
    value = parse_datetime(raw.replace(" ", "+"))  # '+' in a query string may arrive as a space
    if value is None:
        day = parse_date(raw)
        value = datetime.combine(day, time.min) if day else None
    if value is None:
        return None, fail(400, "invalid_request", "updated_since must be ISO 8601, e.g. 2026-09-22T00:00:00Z.")
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value, None


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class BridgePagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class BridgeView(APIView):
    authentication_classes = [PartnerTokenAuthentication]
    permission_classes = [IsBridgePartner]

    def paginate(self, queryset, to_json):
        paginator = BridgePagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        return paginator.get_paginated_response([to_json(obj) for obj in page])


def input_shops():
    return InputSeller.objects.filter(onboarding_completed=True).exclude(seller_type="manufacturer")


class ShopsView(BridgeView):
    """§4. Includes inactive and opted-out shops (is_active: false) so Kikapu can hide them."""

    def get(self, request):
        since, error = parse_updated_since(request)
        if error:
            return error
        shops = input_shops().order_by("pk")
        if since:
            shops = shops.filter(updated_at__gte=since)
        return self.paginate(shops, shop_json)


def filtered_inputs(request):
    items = ShopStockItem.objects.filter(shop__in=input_shops()).select_related("shop", "wholesale_product").order_by("pk")

    shop_param = request.query_params.get("shop_id")
    if shop_param:
        shop_id = parse_prefixed_id(shop_param, "shop")
        items = items.filter(shop_id=shop_id) if shop_id else items.none()

    category = (request.query_params.get("category") or "").strip().lower()
    if category:
        ours = [mine for mine, theirs in KIKAPU_CATEGORY.items() if theirs == category]
        items = items.filter(category__in=ours) if ours else items.none()

    since, error = parse_updated_since(request)
    if error:
        return None, error
    if since:
        # An item also "changes" when its shop changes (paused, renamed) or when it expires,
        # because in_stock / is_active depend on those.
        today = timezone.localdate()
        items = items.filter(
            Q(updated_at__gte=since)
            | Q(shop__updated_at__gte=since)
            | Q(expiry_date__gte=since.date(), expiry_date__lt=today)
        )
    return items, None


class InputsView(BridgeView):
    """§5. Query: ?shop_id=&category=&updated_since="""

    def get(self, request):
        items, error = filtered_inputs(request)
        if error:
            return error
        return self.paginate(items, lambda item: input_json(request, item))


class InputPricesView(BridgeView):
    """Light poll: just price and stock. Same filters as inputs/."""

    def get(self, request):
        items, error = filtered_inputs(request)
        if error:
            return error
        return self.paginate(items, price_json)


class OrdersView(BridgeView):
    """§6. Idempotent on kikapu_order_id: retrying the same order returns the existing one."""

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        errors = {}

        external_id = str(data.get("kikapu_order_id") or "").strip()
        if not external_id or len(external_id) > 64:
            errors["kikapu_order_id"] = ["Required, at most 64 characters."]

        shop_id = parse_prefixed_id(data.get("shop_id"), "shop")
        if shop_id is None:
            errors["shop_id"] = ["Required, e.g. \"shop-104\"."]

        quantities = {}
        items = data.get("items")
        if not isinstance(items, list) or not items:
            errors["items"] = ["At least one item is required."]
        else:
            for index, line in enumerate(items, start=1):
                line = line if isinstance(line, dict) else {}
                input_id = parse_prefixed_id(line.get("input_id"), "input")
                quantity = line.get("quantity")
                if input_id is None or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                    errors.setdefault("items", []).append(f"Item {index} needs an input_id and a whole-number quantity of at least 1.")
                    continue
                quantities[input_id] = quantities.get(input_id, 0) + quantity

        farmer = data.get("farmer") if isinstance(data.get("farmer"), dict) else {}
        farmer_name = str(farmer.get("name") or "").strip()
        farmer_phone = e164(str(farmer.get("phone_number") or ""))
        if not farmer_name:
            errors["farmer.name"] = ["Required."]
        if not farmer_phone:
            errors["farmer.phone_number"] = ["Required, e.g. \"+255711000001\"."]

        if errors:
            return fail(400, "invalid_request", "The order is missing or has invalid fields.", errors)

        existing = FarmerOrder.objects.filter(channel="kikapu", external_order_id=external_id).first()
        if existing:
            return self._replay(existing, shop_id, quantities)

        shop = input_shops().filter(pk=shop_id).first()
        if shop is None:
            return fail(404, "shop_not_found", f"shop-{shop_id} does not exist.")

        try:
            order = services.create_farmer_order(
                shop,
                {pk: Decimal(qty) for pk, qty in quantities.items()},
                external_order_id=external_id,
                farmer_name=farmer_name,
                farmer_phone=farmer_phone,
                delivery_region=str(farmer.get("delivery_region") or ""),
                delivery_notes=str(farmer.get("delivery_notes") or ""),
                farmer_user=_linked_user(farmer.get("mkulima_user_id"), farmer_phone),
            )
        except services.OutOfStockError as exc:
            return fail(409, "unavailable", str(exc))
        except services.StockError as exc:
            return fail(400, "invalid_request", str(exc), {"items": [str(exc)]})
        except IntegrityError:
            # Two identical requests raced; the other one created it.
            existing = FarmerOrder.objects.get(channel="kikapu", external_order_id=external_id)
            return self._replay(existing, shop_id, quantities)

        order = FarmerOrder.objects.prefetch_related("items").get(pk=order.pk)
        return Response(order_json(order), status=status.HTTP_201_CREATED)

    def _replay(self, order, shop_id, quantities):
        same_items = {line.stock_item_id: int(line.quantity) for line in order.items.all()} == quantities
        if order.shop_id != shop_id or not same_items:
            return fail(409, "duplicate_order", f"kikapu_order_id {order.external_order_id} was already used for a different order.")
        return Response(order_json(order), status=status.HTTP_200_OK)


def _linked_user(user_id, phone):
    """Link the order to a Mkulima Smart account only when the id and phone number agree."""
    if not str(user_id or "").isdigit():
        return None
    user = get_user_model().objects.filter(pk=int(user_id)).first()
    return user if user and e164(user.phone_number) == phone else None


class OrderDetailView(BridgeView):
    def get(self, request, order_id):
        pk = parse_prefixed_id(order_id, "MS")
        order = get_object_or_404(FarmerOrder.objects.prefetch_related("items"), pk=pk, channel="kikapu")
        return Response(order_json(order))

"""
JSON output for the mobile API. Input is validated by the Django forms in forms.py
(the same ones the web pages use), so these serializers are read-only.
"""
from django.db import models
from rest_framework import serializers

from operations.models import InputSeller

from . import services
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
    WholesaleProductImage,
)


class NumberDecimalField(serializers.DecimalField):
    """Money and quantities as JSON numbers (not strings), which is easier to use from Dart."""

    def __init__(self, *args, **kwargs):
        kwargs["coerce_to_string"] = False
        super().__init__(*args, **kwargs)


class BaseSerializer(serializers.ModelSerializer):
    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        models.DecimalField: NumberDecimalField,
    }


def absolute_url(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


class SellerSerializer(BaseSerializer):
    seller_type_display = serializers.CharField(source="get_seller_type_display", read_only=True)
    role = serializers.SerializerMethodField()
    certificate_file = serializers.SerializerMethodField()

    class Meta:
        model = InputSeller
        fields = [
            "id", "business_name", "seller_name", "phone_number", "location", "region", "district",
            "latitude", "longitude", "seller_type", "seller_type_display", "role", "products_offered",
            "certification_details", "certificate_file", "list_on_kikapu", "onboarding_completed",
        ]

    def get_role(self, obj):
        return "manufacturer" if obj.seller_type == "manufacturer" else "shop"

    def get_certificate_file(self, obj):
        return absolute_url(self.context.get("request"), obj.certificate_file)


class SellerBriefSerializer(BaseSerializer):
    class Meta:
        model = InputSeller
        fields = ["id", "business_name", "phone_number", "location"]


class ProductImageSerializer(BaseSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = WholesaleProductImage
        fields = ["id", "url", "is_primary"]

    def get_url(self, obj):
        return absolute_url(self.context.get("request"), obj.image)


class WholesaleProductSerializer(BaseSerializer):
    manufacturer = SellerBriefSerializer(read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    registration_authority_display = serializers.CharField(source="get_registration_authority_display", read_only=True)
    toxicity_class_display = serializers.CharField(source="get_toxicity_class_display", read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    cover_image = serializers.SerializerMethodField()
    in_my_stock = serializers.SerializerMethodField()
    soil_type_display = serializers.CharField(read_only=True)

    class Meta:
        model = WholesaleProduct
        fields = [
            "id", "manufacturer", "name", "brand", "category", "category_display", "pack_size", "unit", "unit_display",
            "wholesale_price", "suggested_retail_price", "min_order_quantity", "stock_available",
            "composition", "registration_authority", "registration_authority_display", "registration_number",
            "target_crops", "suitable_regions", "soil_type", "soil_type_display",
            "usage_instructions", "toxicity_class", "toxicity_class_display", "safety_precautions",
            "seed_variety", "maturity_days", "germination_rate", "shelf_life_months", "description", "is_active",
            "cover_image", "images", "in_my_stock", "created_at", "updated_at",
        ]

    def get_cover_image(self, obj):
        image = obj.primary_image
        return absolute_url(self.context.get("request"), image.image) if image else None

    def get_in_my_stock(self, obj):
        # Only meaningful for shops browsing the catalog; the view passes the set of stocked product ids.
        stocked = self.context.get("stocked_ids")
        return None if stocked is None else obj.pk in stocked


class StockItemSerializer(BaseSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    image = serializers.SerializerMethodField()
    is_low_stock = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    expires_soon = serializers.BooleanField(read_only=True)
    margin_percent = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ShopStockItem
        fields = [
            "id", "name", "brand", "category", "category_display", "sku", "unit", "unit_display",
            "cost_price", "selling_price", "quantity", "reorder_level", "batch_number", "expiry_date",
            "image", "is_active", "wholesale_product", "is_low_stock", "is_expired", "expires_soon",
            "margin_percent", "created_at", "updated_at",
        ]

    def get_image(self, obj):
        return absolute_url(self.context.get("request"), obj.image)


class StockMovementSerializer(BaseSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "reason", "reason_display", "change", "balance_after", "reference", "note", "created_at"]


class SaleItemSerializer(BaseSerializer):
    class Meta:
        model = SaleItem
        fields = ["id", "stock_item", "product_name", "quantity", "unit_price", "line_total"]


class SaleSerializer(BaseSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    change_due = NumberDecimalField(max_digits=14, decimal_places=2, read_only=True)
    balance_due = NumberDecimalField(max_digits=14, decimal_places=2, read_only=True)
    sold_by = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            "id", "receipt_number", "created_at", "channel", "customer_name", "customer_phone", "payment_method",
            "payment_method_display", "subtotal", "discount", "total", "amount_paid", "change_due", "balance_due",
            "sold_by", "items",
        ]

    def get_sold_by(self, obj):
        return obj.sold_by.get_short_name() if obj.sold_by else None


class SaleListSerializer(SaleSerializer):
    item_count = serializers.IntegerField(read_only=True)

    class Meta(SaleSerializer.Meta):
        fields = [f for f in SaleSerializer.Meta.fields if f != "items"] + ["item_count"]


class PurchaseOrderItemSerializer(BaseSerializer):
    line_total = NumberDecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "wholesale_product", "product_name", "quantity", "unit_price", "line_total"]


class PurchaseOrderSerializer(BaseSerializer):
    shop = SellerBriefSerializer(read_only=True)
    manufacturer = SellerBriefSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "order_number", "status", "status_display", "shop", "manufacturer", "total", "notes",
            "manufacturer_note", "created_at", "updated_at", "received_at", "items", "allowed_actions",
        ]

    def get_allowed_actions(self, obj):
        """What the current viewer may do next, so the app can show only valid buttons."""
        if self.context.get("viewer") == "manufacturer":
            return [status for status, sources in services.MANUFACTURER_TRANSITIONS.items() if obj.status in sources]
        actions = []
        if obj.status in services.SHOP_TRANSITIONS["cancelled"]:
            actions.append("cancel")
        if obj.status == "dispatched":
            actions.append("receive")
        return actions


class PurchaseOrderListSerializer(PurchaseOrderSerializer):
    item_count = serializers.IntegerField(read_only=True)

    class Meta(PurchaseOrderSerializer.Meta):
        fields = [f for f in PurchaseOrderSerializer.Meta.fields if f != "items"] + ["item_count"]


class FarmerOrderItemSerializer(BaseSerializer):
    class Meta:
        model = FarmerOrderItem
        fields = ["id", "stock_item", "product_name", "quantity", "unit_price", "line_total"]


class FarmerOrderSerializer(BaseSerializer):
    order_number = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    allowed_actions = serializers.ListField(source="allowed_next_statuses", read_only=True)
    items = FarmerOrderItemSerializer(many=True, read_only=True)
    farmer_notified = serializers.SerializerMethodField()

    class Meta:
        model = FarmerOrder
        fields = [
            "id", "order_number", "channel", "channel_display", "external_order_id", "status", "status_display",
            "farmer_name", "farmer_phone", "delivery_region", "delivery_notes", "total", "shop_note", "sale",
            "items", "allowed_actions", "farmer_notified", "created_at", "updated_at",
        ]

    def get_farmer_notified(self, obj):
        """State of the latest WhatsApp update: delivered / pending / failed, or null if none was sent."""
        webhook = obj.kikapu_webhooks.order_by("-created_at").first() if hasattr(obj, "kikapu_webhooks") else None
        return {"status": webhook.status, "state": webhook.state} if webhook else None

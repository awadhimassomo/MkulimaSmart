from django.contrib import admin

from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    ShopStockItem,
    StockMovement,
    WholesaleProduct,
    WholesaleProductImage,
)


class WholesaleProductImageInline(admin.TabularInline):
    model = WholesaleProductImage
    extra = 1


@admin.register(WholesaleProduct)
class WholesaleProductAdmin(admin.ModelAdmin):
    list_display = ("name", "manufacturer", "category", "pack_size", "wholesale_price", "stock_available", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "manufacturer__business_name")
    inlines = [WholesaleProductImageInline]


@admin.register(ShopStockItem)
class ShopStockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "quantity", "reorder_level", "cost_price", "selling_price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "sku", "shop__business_name")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("stock_item", "reason", "change", "balance_after", "reference", "created_at")
    list_filter = ("reason",)
    search_fields = ("stock_item__name", "reference")


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "shop", "total", "payment_method", "created_at")
    list_filter = ("payment_method",)
    search_fields = ("receipt_number", "customer_name", "customer_phone")
    inlines = [SaleItemInline]


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "shop", "manufacturer", "status", "total", "created_at")
    list_filter = ("status",)
    search_fields = ("order_number", "shop__business_name", "manufacturer__business_name")
    inlines = [PurchaseOrderItemInline]

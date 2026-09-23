from django.contrib import admin

from .models import HarvestTraceLot, TraceabilityPlanting


@admin.register(TraceabilityPlanting)
class TraceabilityPlantingAdmin(admin.ModelAdmin):
    list_display = (
        "planting_code",
        "crop_type",
        "variety",
        "farmer",
        "farm",
        "source_batch",
        "planting_date",
        "status",
    )
    list_filter = ("status", "crop_type", "planting_date")
    search_fields = ("planting_code", "crop_type", "variety", "supplier_trace_code", "farmer__phone_number", "farm__name")


@admin.register(HarvestTraceLot)
class HarvestTraceLotAdmin(admin.ModelAdmin):
    list_display = ("trace_code", "lot_code", "planting", "harvest_date", "is_public", "status")
    list_filter = ("status", "is_public", "harvest_date")
    search_fields = ("trace_code", "lot_code", "planting__planting_code", "planting__crop_type")
    readonly_fields = ("trace_code", "lot_code", "qr_code")

from django.contrib import admin

from .models import FarmActivity, FarmInputUsage, InputSeller, InspectionLog, PlantingRecord, SeedlingBatch


@admin.register(InputSeller)
class InputSellerAdmin(admin.ModelAdmin):
    list_display = ("seller_name", "business_name", "user", "seller_type", "onboarding_completed", "phone_number", "location", "is_active")
    list_filter = ("seller_type", "onboarding_completed", "is_active")
    search_fields = ("seller_name", "business_name", "phone_number", "location")


@admin.register(SeedlingBatch)
class SeedlingBatchAdmin(admin.ModelAdmin):
    list_display = ("seedling_batch_id", "seedling_type", "seller", "quantity_available", "unit", "batch_date")
    list_filter = ("unit", "batch_date", "seller")
    search_fields = ("seedling_batch_id", "seedling_type", "variety", "source_name")
    readonly_fields = ("seedling_batch_id", "qr_code")


class FarmActivityInline(admin.TabularInline):
    model = FarmActivity
    extra = 0


class FarmInputUsageInline(admin.TabularInline):
    model = FarmInputUsage
    extra = 0


class InspectionLogInline(admin.TabularInline):
    model = InspectionLog
    extra = 0


@admin.register(PlantingRecord)
class PlantingRecordAdmin(admin.ModelAdmin):
    list_display = (
        "planting_cycle_id",
        "crop_type",
        "farmer_name",
        "farm_name",
        "seedling_batch",
        "planting_date",
        "expected_harvest_date",
        "verification_status",
    )
    list_filter = ("verification_status", "planting_date", "crop_type")
    search_fields = ("planting_cycle_id", "crop_type", "farm__name", "farm_name", "farmer__phone_number", "farmer_phone", "farmer_name")
    inlines = [FarmActivityInline, FarmInputUsageInline, InspectionLogInline]


@admin.register(FarmActivity)
class FarmActivityAdmin(admin.ModelAdmin):
    list_display = ("planting_record", "activity_type", "activity_date", "created_by")
    list_filter = ("activity_type", "activity_date")
    search_fields = ("planting_record__planting_cycle_id", "notes")


@admin.register(FarmInputUsage)
class FarmInputUsageAdmin(admin.ModelAdmin):
    list_display = ("planting_record", "input_type", "product_name", "quantity", "application_date")
    list_filter = ("input_type", "application_date")
    search_fields = ("planting_record__planting_cycle_id", "product_name")


@admin.register(InspectionLog)
class InspectionLogAdmin(admin.ModelAdmin):
    list_display = ("planting_record", "visit_date", "visited_by", "purpose")
    list_filter = ("visit_date",)
    search_fields = ("planting_record__planting_cycle_id", "purpose", "findings")

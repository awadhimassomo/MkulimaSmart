from django.contrib import admin

from .models import DatasetExport, LabeledImage


@admin.register(LabeledImage)
class LabeledImageAdmin(admin.ModelAdmin):
    list_display = ("crop", "problem", "split", "is_rejected", "label_source", "labeled_by", "labeled_at")
    list_filter = ("split", "is_rejected", "label_source", "problem_type")
    search_fields = ("crop", "problem")
    raw_id_fields = ("message", "labeled_by")


@admin.register(DatasetExport)
class DatasetExportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "exported_by", "image_count", "class_count", "skipped")
    readonly_fields = ("exported_by", "created_at", "image_count", "class_count", "split_counts", "skipped")

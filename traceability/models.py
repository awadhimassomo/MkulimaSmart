import io
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from operations.models import SeedlingBatch
from website.models import Farm


def build_qr_image(payload: str) -> ContentFile:
    buffer = io.BytesIO()

    try:
        import qrcode  # type: ignore

        image = qrcode.make(payload)
        image.save(buffer, format="PNG")
    except Exception:
        buffer.write(
            bytes.fromhex(
                "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
                "0000000D49444154789C6360000002000154A24F5D0000000049454E44AE426082"
            )
        )

    return ContentFile(buffer.getvalue())


class TraceabilityPlanting(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("harvested", "Harvested"),
        ("archived", "Archived"),
    ]

    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="traceability_plantings")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="traceability_plantings")
    source_batch = models.ForeignKey(
        SeedlingBatch,
        on_delete=models.SET_NULL,
        related_name="traceability_plantings",
        blank=True,
        null=True,
    )
    planting_code = models.CharField(max_length=40, unique=True, editable=False)
    supplier_trace_code = models.CharField(max_length=64, blank=True)
    crop_type = models.CharField(max_length=120)
    variety = models.CharField(max_length=120, blank=True)
    quantity_planted = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    unit = models.CharField(max_length=30, default="seedlings")
    planting_date = models.DateField()
    farming_method = models.CharField(max_length=120, blank=True)
    area_planted = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    area_unit = models.CharField(max_length=30, blank=True)
    soil_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    location_summary = models.CharField(max_length=255, blank=True)
    expected_days_to_harvest = models.PositiveIntegerField(blank=True, null=True)
    expected_harvest_start = models.DateField(blank=True, null=True)
    expected_harvest_end = models.DateField(blank=True, null=True)
    estimated_yield = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    estimated_yield_unit = models.CharField(max_length=30, blank=True)
    prediction_summary = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.planting_code} - {self.crop_type}"

    def save(self, *args, **kwargs):
        if not self.planting_code:
            self.planting_code = f"TP-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        if not self.supplier_trace_code and self.source_batch:
            self.supplier_trace_code = self.source_batch.seedling_batch_id
        if not self.location_summary and self.farm_id:
            self.location_summary = self.farm.location
        super().save(*args, **kwargs)


class HarvestTraceLot(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("inactive", "Inactive"),
    ]

    planting = models.OneToOneField(TraceabilityPlanting, on_delete=models.CASCADE, related_name="harvest_lot")
    trace_code = models.CharField(max_length=40, unique=True, editable=False)
    lot_code = models.CharField(max_length=40, unique=True, editable=False)
    harvest_date = models.DateField(blank=True, null=True)
    actual_output_quantity = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    actual_output_unit = models.CharField(max_length=30, blank=True)
    certifications = models.JSONField(blank=True, null=True)
    public_message = models.CharField(max_length=255, blank=True)
    is_public = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    qr_code = models.ImageField(upload_to="traceability/harvest_qr/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.trace_code

    def get_public_url(self):
        return reverse("traceability:harvest_public_lookup", kwargs={"trace_code": self.trace_code})

    def ensure_qr_code(self):
        if not self.qr_code:
            payload = self.get_public_url()
            file_name = f"{self.trace_code}.png"
            self.qr_code.save(file_name, build_qr_image(payload), save=False)

    def save(self, *args, **kwargs):
        if not self.trace_code:
            self.trace_code = f"HT-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        if not self.lot_code:
            self.lot_code = f"LOT-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
        if not self.qr_code:
            self.ensure_qr_code()
            super().save(update_fields=["qr_code"])


def estimate_harvest_window(crop_type: str, variety: str, planting_date, override_days=None):
    crop_defaults = {
        "tomato": 90,
        "maize": 120,
        "rice": 120,
        "onion": 110,
        "cabbage": 90,
        "pepper": 95,
    }
    days = override_days or crop_defaults.get((crop_type or "").strip().lower(), 100)
    start = planting_date + timedelta(days=days)
    end = start + timedelta(days=7)
    return days, start, end


def estimate_yield(quantity_planted, area_planted=None):
    quantity = Decimal(quantity_planted or 0)
    if area_planted:
        return (quantity * Decimal("1.50")) + Decimal(area_planted or 0)
    return quantity * Decimal("1.25")

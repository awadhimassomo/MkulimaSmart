import io
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from website.models import Farm


def build_qr_image(payload: str) -> ContentFile:
    """
    Create a QR image when the qrcode package is available.
    Fall back to a tiny valid PNG in thin environments.
    """
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


class InputSeller(models.Model):
    SELLER_TYPE_CHOICES = [
        ("seedling_seller", "Seedling Seller"),
        ("nursery_operator", "Nursery Operator"),
        ("agro_input_dealer", "Agro-Input Dealer"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="input_seller_profile",
        blank=True,
        null=True,
    )
    seller_name = models.CharField(max_length=255)
    business_name = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=30)
    seller_type = models.CharField(max_length=30, choices=SELLER_TYPE_CHOICES)
    location = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seller_name"]

    def __str__(self):
        return self.business_name or self.seller_name

    @classmethod
    def get_or_create_for_user(cls, user):
        seller = cls.objects.filter(user=user).first()
        if seller:
            return seller

        display_name = user.get_full_name().strip() or user.phone_number
        seller, _ = cls.objects.get_or_create(
            phone_number=user.phone_number,
            defaults={
                "user": user,
                "seller_name": display_name,
                "business_name": display_name,
                "seller_type": "seedling_seller",
                "location": user.address or "Tanzania",
                "is_active": True,
            },
        )

        updates = []
        if seller.user_id != user.id:
            seller.user = user
            updates.append("user")
        if not seller.seller_name:
            seller.seller_name = display_name
            updates.append("seller_name")
        if not seller.business_name:
            seller.business_name = display_name
            updates.append("business_name")
        if not seller.location:
            seller.location = user.address or "Tanzania"
            updates.append("location")
        if updates:
            seller.save(update_fields=updates)
        return seller


class SeedlingBatch(models.Model):
    UNIT_CHOICES = [
        ("seedlings", "Seedlings"),
        ("trays", "Trays"),
        ("bags", "Bags"),
        ("bundles", "Bundles"),
        ("pieces", "Pieces"),
    ]

    seller = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="seedling_batches")
    seedling_batch_id = models.CharField(max_length=32, unique=True, editable=False)
    seedling_type = models.CharField(max_length=120)
    variety = models.CharField(max_length=120, blank=True)
    source_name = models.CharField(max_length=255, blank=True)
    quantity_available = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="seedlings")
    qr_code = models.ImageField(upload_to="operations/qr_codes/", blank=True)
    batch_date = models.DateField(default=timezone.now)
    recommended_planting_until = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.seedling_batch_id} - {self.seedling_type}"

    def get_absolute_url(self):
        return reverse("marketplace:supplier_dashboard")

    def get_scan_url(self):
        return reverse("marketplace:batch_scan", kwargs={"seedling_batch_id": self.seedling_batch_id})

    def get_absolute_scan_url(self):
        base_url = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
        return f"{base_url}{self.get_scan_url()}"

    def ensure_qr_code(self):
        if not self.qr_code:
            payload = self.get_absolute_scan_url()
            file_name = f"{self.seedling_batch_id}.png"
            self.qr_code.save(file_name, build_qr_image(payload), save=False)

    def save(self, *args, **kwargs):
        if not self.seedling_batch_id:
            self.seedling_batch_id = f"SB-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"

        super().save(*args, **kwargs)

        if not self.qr_code:
            self.ensure_qr_code()
            super().save(update_fields=["qr_code"])


class PlantingRecord(models.Model):
    FARM_SIZE_UNIT_CHOICES = [
        ("hectares", "Hectares"),
        ("acres", "Acres"),
    ]

    VERIFICATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("unverified", "Unverified"),
        ("verified", "Verified"),
        ("flagged", "Flagged"),
    ]

    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="planting_records")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="planting_records")
    seedling_batch = models.ForeignKey(SeedlingBatch, on_delete=models.SET_NULL, related_name="planting_records", blank=True, null=True)
    planting_cycle_id = models.CharField(max_length=40, unique=True, blank=True)
    farmer_name = models.CharField(max_length=255, blank=True)
    farmer_phone = models.CharField(max_length=30, blank=True)
    farmer_email = models.EmailField(blank=True)
    farm_name = models.CharField(max_length=255, blank=True)
    crop_type = models.CharField(max_length=120)
    planting_date = models.DateField()
    quantity_planted = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))], blank=True, null=True)
    unit = models.CharField(max_length=30, default="seedlings")
    location = models.CharField(max_length=255, blank=True)
    farm_location = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=120, blank=True)
    farm_size = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    farm_size_unit = models.CharField(max_length=20, choices=FARM_SIZE_UNIT_CHOICES, default="hectares")
    expected_harvest_date = models.DateField(blank=True, null=True)
    expected_quantity = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    expected_yield = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    boundary = models.JSONField(blank=True, null=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS_CHOICES, default="pending")
    verification_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to="operations/planting_records/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-planting_date", "-created_at"]

    def __str__(self):
        return f"{self.planting_cycle_id or self.pk} - {self.crop_type}"

    def clean(self):
        super().clean()
        if self.expected_harvest_date and self.planting_date and self.expected_harvest_date < self.planting_date:
            raise ValidationError({"expected_harvest_date": "Expected harvest date cannot be earlier than planting date."})

    def save(self, *args, **kwargs):
        if not self.planting_cycle_id:
            self.planting_cycle_id = f"PC-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"

        if not self.farmer_name and self.farmer_id:
            self.farmer_name = self.farmer.get_full_name()
        if not self.farmer_phone and self.farmer_id:
            self.farmer_phone = self.farmer.phone_number
        if not self.farmer_email and self.farmer_id:
            self.farmer_email = self.farmer.email or ""
        if not self.farm_name and self.farm_id:
            self.farm_name = self.farm.name
        if not self.farm_location:
            self.farm_location = self.location or self.farm.location
        if not self.location:
            self.location = self.farm_location
        if not self.farm_size and self.farm_id:
            self.farm_size = self.farm.size
        if self.expected_quantity is None and self.expected_yield is not None:
            self.expected_quantity = self.expected_yield
        if self.expected_yield is None and self.expected_quantity is not None:
            self.expected_yield = self.expected_quantity

        super().save(*args, **kwargs)


class FarmActivity(models.Model):
    ACTIVITY_TYPE_CHOICES = [
        ("planting", "Planting"),
        ("watering", "Watering"),
        ("fertilizer_application", "Fertilizer Application"),
        ("pesticide_application", "Pesticide Application"),
        ("pruning", "Pruning"),
        ("transplanting", "Transplanting"),
        ("disease_observation", "Disease Observation"),
        ("harvest_preparation", "Harvest Preparation"),
        ("inspection_visit", "Inspection Visit"),
    ]

    planting_record = models.ForeignKey(PlantingRecord, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=40, choices=ACTIVITY_TYPE_CHOICES)
    activity_date = models.DateField(default=timezone.now)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    unit = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to="operations/activities/", blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="farm_activities_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-activity_date", "-created_at"]

    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.planting_record}"


class FarmInputUsage(models.Model):
    planting_record = models.ForeignKey(PlantingRecord, on_delete=models.CASCADE, related_name="input_usages")
    input_type = models.CharField(max_length=120)
    product_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=30, blank=True)
    application_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-application_date", "-id"]

    def __str__(self):
        return f"{self.product_name} for {self.planting_record}"


class InspectionLog(models.Model):
    planting_record = models.ForeignKey(PlantingRecord, on_delete=models.CASCADE, related_name="inspection_logs")
    visit_date = models.DateField(default=timezone.now)
    visited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="inspection_logs")
    purpose = models.CharField(max_length=255)
    findings = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    photo = models.ImageField(upload_to="operations/inspections/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]

    def __str__(self):
        return f"Inspection on {self.visit_date} - {self.planting_record}"

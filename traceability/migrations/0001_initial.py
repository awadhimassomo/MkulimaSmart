import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("operations", "0001_initial"),
        ("website", "0004_farm_boundary_point_count_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TraceabilityPlanting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("planting_code", models.CharField(editable=False, max_length=40, unique=True)),
                ("supplier_trace_code", models.CharField(blank=True, max_length=64)),
                ("crop_type", models.CharField(max_length=120)),
                ("variety", models.CharField(blank=True, max_length=120)),
                ("quantity_planted", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("unit", models.CharField(default="seedlings", max_length=30)),
                ("planting_date", models.DateField()),
                ("farming_method", models.CharField(blank=True, max_length=120)),
                ("area_planted", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("area_unit", models.CharField(blank=True, max_length=30)),
                ("soil_notes", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("location_summary", models.CharField(blank=True, max_length=255)),
                ("expected_days_to_harvest", models.PositiveIntegerField(blank=True, null=True)),
                ("expected_harvest_start", models.DateField(blank=True, null=True)),
                ("expected_harvest_end", models.DateField(blank=True, null=True)),
                ("estimated_yield", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("estimated_yield_unit", models.CharField(blank=True, max_length=30)),
                ("prediction_summary", models.JSONField(blank=True, null=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("harvested", "Harvested"), ("archived", "Archived")], default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="traceability_plantings", to="website.farm")),
                ("farmer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="traceability_plantings", to=settings.AUTH_USER_MODEL)),
                ("source_batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="traceability_plantings", to="operations.seedlingbatch")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="HarvestTraceLot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trace_code", models.CharField(editable=False, max_length=40, unique=True)),
                ("lot_code", models.CharField(editable=False, max_length=40, unique=True)),
                ("harvest_date", models.DateField(blank=True, null=True)),
                ("actual_output_quantity", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("actual_output_unit", models.CharField(blank=True, max_length=30)),
                ("certifications", models.JSONField(blank=True, null=True)),
                ("public_message", models.CharField(blank=True, max_length=255)),
                ("is_public", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("inactive", "Inactive")], default="draft", max_length=20)),
                ("qr_code", models.ImageField(blank=True, upload_to="traceability/harvest_qr/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("planting", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="harvest_lot", to="traceability.traceabilityplanting")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]

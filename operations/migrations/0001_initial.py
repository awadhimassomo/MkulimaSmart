from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("website", "0002_alter_user_managers_remove_user_username_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="InputSeller",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seller_name", models.CharField(max_length=255)),
                ("business_name", models.CharField(blank=True, max_length=255)),
                ("phone_number", models.CharField(max_length=30)),
                ("seller_type", models.CharField(choices=[("seedling_seller", "Seedling Seller"), ("nursery_operator", "Nursery Operator"), ("agro_input_dealer", "Agro-Input Dealer")], max_length=30)),
                ("location", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["seller_name"]},
        ),
        migrations.CreateModel(
            name="SeedlingBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seedling_batch_id", models.CharField(editable=False, max_length=32, unique=True)),
                ("seedling_type", models.CharField(max_length=120)),
                ("variety", models.CharField(blank=True, max_length=120)),
                ("source_name", models.CharField(blank=True, max_length=255)),
                ("quantity_available", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("unit", models.CharField(choices=[("seedlings", "Seedlings"), ("trays", "Trays"), ("bags", "Bags"), ("bundles", "Bundles"), ("pieces", "Pieces")], default="seedlings", max_length=20)),
                ("qr_code", models.ImageField(blank=True, upload_to="operations/qr_codes/")),
                ("batch_date", models.DateField(default=django.utils.timezone.now)),
                ("recommended_planting_until", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seedling_batches", to="operations.inputseller")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PlantingRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("planting_cycle_id", models.CharField(blank=True, max_length=40, unique=True)),
                ("crop_type", models.CharField(max_length=120)),
                ("planting_date", models.DateField()),
                ("quantity_planted", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("unit", models.CharField(default="seedlings", max_length=30)),
                ("location", models.CharField(blank=True, max_length=255)),
                ("expected_harvest_date", models.DateField(blank=True, null=True)),
                ("expected_yield", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("latitude", models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ("boundary", models.JSONField(blank=True, null=True)),
                ("verification_status", models.CharField(choices=[("pending", "Pending"), ("unverified", "Unverified"), ("verified", "Verified"), ("flagged", "Flagged")], default="pending", max_length=20)),
                ("verification_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("notes", models.TextField(blank=True)),
                ("photo", models.ImageField(blank=True, null=True, upload_to="operations/planting_records/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="planting_records", to="website.farm")),
                ("farmer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="planting_records", to=settings.AUTH_USER_MODEL)),
                ("seedling_batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planting_records", to="operations.seedlingbatch")),
            ],
            options={"ordering": ["-planting_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="InspectionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visit_date", models.DateField(default=django.utils.timezone.now)),
                ("purpose", models.CharField(max_length=255)),
                ("findings", models.TextField(blank=True)),
                ("recommendations", models.TextField(blank=True)),
                ("photo", models.ImageField(blank=True, null=True, upload_to="operations/inspections/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("planting_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inspection_logs", to="operations.plantingrecord")),
                ("visited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inspection_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-visit_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="FarmInputUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("input_type", models.CharField(max_length=120)),
                ("product_name", models.CharField(max_length=255)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=12)),
                ("unit", models.CharField(blank=True, max_length=30)),
                ("application_date", models.DateField(default=django.utils.timezone.now)),
                ("notes", models.TextField(blank=True)),
                ("planting_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="input_usages", to="operations.plantingrecord")),
            ],
            options={"ordering": ["-application_date", "-id"]},
        ),
        migrations.CreateModel(
            name="FarmActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity_type", models.CharField(choices=[("planting", "Planting"), ("watering", "Watering"), ("fertilizer_application", "Fertilizer Application"), ("pesticide_application", "Pesticide Application"), ("pruning", "Pruning"), ("transplanting", "Transplanting"), ("disease_observation", "Disease Observation"), ("harvest_preparation", "Harvest Preparation"), ("inspection_visit", "Inspection Visit")], max_length=40)),
                ("activity_date", models.DateField(default=django.utils.timezone.now)),
                ("quantity", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("unit", models.CharField(blank=True, max_length=30)),
                ("notes", models.TextField(blank=True)),
                ("photo", models.ImageField(blank=True, null=True, upload_to="operations/activities/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="farm_activities_created", to=settings.AUTH_USER_MODEL)),
                ("planting_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="operations.plantingrecord")),
            ],
            options={"ordering": ["-activity_date", "-created_at"]},
        ),
    ]

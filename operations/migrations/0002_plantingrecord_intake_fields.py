from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="plantingrecord",
            name="expected_quantity",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farm_location",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farm_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farm_size",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farm_size_unit",
            field=models.CharField(choices=[("hectares", "Hectares"), ("acres", "Acres")], default="hectares", max_length=20),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farmer_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farmer_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="farmer_phone",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="plantingrecord",
            name="region",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="plantingrecord",
            name="quantity_planted",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))]),
        ),
    ]

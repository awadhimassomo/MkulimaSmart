import django.utils.timezone
from django.db import migrations, models

import operations.models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0005_alter_inputseller_seller_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="inputseller",
            name="region",
            field=models.CharField(blank=True, choices=operations.models.TANZANIA_REGIONS, max_length=40),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="district",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="list_on_kikapu",
            field=models.BooleanField(
                default=True,
                help_text="Shows your in-stock inputs to farmers on Kikapu's WhatsApp number.",
                verbose_name="Accept farmer orders via Kikapu WhatsApp",
            ),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]

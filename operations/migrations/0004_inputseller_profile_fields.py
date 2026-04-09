from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0003_inputseller_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="inputseller",
            name="certificate_file",
            field=models.FileField(blank=True, null=True, upload_to="operations/seller_certificates/"),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="certification_details",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="onboarding_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="inputseller",
            name="products_offered",
            field=models.JSONField(blank=True, default=list),
        ),
    ]

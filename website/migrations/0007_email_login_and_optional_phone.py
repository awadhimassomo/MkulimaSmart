from django.db import migrations, models


def blank_emails_to_null(apps, schema_editor):
    User = apps.get_model("website", "User")
    users = list(User.objects.exclude(email__isnull=True).values_list("pk", "email"))
    for user_id, current_email in users:
        email = (current_email or "").strip().lower()
        User.objects.filter(pk=user_id).update(email=email or None)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0006_seed_supplier_categories"),
    ]

    operations = [
        # The column must accept NULL before blank emails can be turned into NULL, and it cannot be
        # unique while several blanks still exist, so: nullable first, clean the data, then unique.
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name="Email Address"),
        ),
        migrations.RunPython(blank_emails_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name="Email Address"),
        ),
        migrations.AlterField(
            model_name="user",
            name="phone_number",
            field=models.CharField(blank=True, max_length=15, null=True, unique=True, verbose_name="Phone Number"),
        ),
    ]

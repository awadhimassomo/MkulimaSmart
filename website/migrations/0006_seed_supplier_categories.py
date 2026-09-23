from django.db import migrations

from website.category_defaults import DEFAULT_SUPPLIER_CATEGORIES


def seed_supplier_categories(apps, schema_editor):
    Category = apps.get_model("website", "Category")

    for category in DEFAULT_SUPPLIER_CATEGORIES:
        Category.objects.update_or_create(
            slug=category["slug"],
            defaults={
                "name": category["name"],
                "description": category["description"],
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0005_user_is_lead_farmer"),
    ]

    operations = [
        migrations.RunPython(seed_supplier_categories, migrations.RunPython.noop),
    ]

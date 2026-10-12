import re

from django.db import migrations

BRAND_LINE = re.compile(r"^[ \t]*Brand:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


def move_brand_out_of_the_description(apps, schema_editor):
    """
    Listings made before listings had a Brand field carry it as a "Brand: X" line in the description. Move it into the
    brand field (so it is shown in bold) and take the line out of the text.
    """
    Product = apps.get_model("website", "Product")
    for product in Product.objects.filter(brand="", description__contains="Brand:"):
        match = BRAND_LINE.search(product.description or "")
        if not match:
            continue
        description = BRAND_LINE.sub("", product.description, count=1)
        description = re.sub(r"\n{3,}", "\n\n", description).strip()
        product.brand = match.group(1)[:120]
        product.description = description or product.name
        product.save(update_fields=["brand", "description"])


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0009_order_buyer_name_order_delivery_fee_and_more"),
    ]

    operations = [
        migrations.RunPython(move_brand_out_of_the_description, migrations.RunPython.noop),
    ]

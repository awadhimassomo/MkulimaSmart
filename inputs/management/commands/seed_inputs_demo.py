"""
Create a demo manufacturer and a demo input shop for local testing.

    python manage.py seed_inputs_demo

Logins (phone / password):  0711000001 / demo12345 (shop)
                            0711000002 / demo12345 (manufacturer)
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from inputs import services
from inputs.models import ShopStockItem, WholesaleProduct
from operations.models import InputSeller

PASSWORD = "demo12345"

CATALOG = [
    ("Urea 46% N", "fertilizer", "50 kg", "bag", 62000, 72000, 5, 400),
    ("DAP 18-46-0", "fertilizer", "50 kg", "bag", 78000, 90000, 5, 250),
    ("CAN 26%", "fertilizer", "50 kg", "bag", 55000, 64000, 5, 300),
    ("Hybrid Maize Seed H614", "seeds", "2 kg", "packet", 9500, 12000, 20, 1000),
    ("Bean Seed Lyamungu 90", "seeds", "1 kg", "packet", 6000, 8000, 20, 600),
    ("Duduba Insecticide", "pesticides", "1 litre", "bottle", 14000, 18000, 12, 300),
]

# Extra product details. Registration numbers are clearly marked DEMO; they are not real registrations.
DETAILS = {
    "Urea 46% N": {"brand": "Kilimo Bora", "composition": "46-0-0 (Nitrogen 46%)", "registration_number": "DEMO-TFRA-0001",
                   "target_crops": ["Maize", "Rice", "Sorghum"], "usage_instructions": "Top-dress 1 bag per acre 3-4 weeks after planting.",
                   "shelf_life_months": 24},
    "DAP 18-46-0": {"brand": "Kilimo Bora", "composition": "18-46-0", "registration_number": "DEMO-TFRA-0002",
                    "target_crops": ["Maize", "Beans", "Sunflower"], "usage_instructions": "Apply 1 bag per acre at planting, in the planting hole."},
    "CAN 26%": {"brand": "Kilimo Bora", "composition": "26% N + Calcium", "registration_number": "DEMO-TFRA-0003",
                "target_crops": ["Maize", "Coffee", "Tomato"]},
    "Hybrid Maize Seed H614": {"brand": "Mbegu Bora", "seed_variety": "H614", "registration_number": "DEMO-TOSCI-0101",
                               "maturity_days": 150, "germination_rate": Decimal("90"), "target_crops": ["Maize"], "shelf_life_months": 12},
    "Bean Seed Lyamungu 90": {"brand": "Mbegu Bora", "seed_variety": "Lyamungu 90", "registration_number": "DEMO-TOSCI-0102",
                              "maturity_days": 85, "germination_rate": Decimal("85"), "target_crops": ["Beans"], "shelf_life_months": 12},
    "Duduba Insecticide": {"brand": "Kinga", "composition": "Chlorpyrifos 450 g/L + Cypermethrin 50 g/L EC",
                           "registration_number": "DEMO-TPHPA-0201", "toxicity_class": "II",
                           "safety_precautions": "Wear gloves, mask and long sleeves. Pre-harvest interval 14 days.",
                           "usage_instructions": "30 ml per 20 L knapsack sprayer.", "target_crops": ["Maize", "Beans", "Tomato"],
                           "shelf_life_months": 24},
}


class Command(BaseCommand):
    help = "Create demo manufacturer and shop accounts with catalog, stock and an order."

    def _seller(self, phone, name, seller_type, location, region):
        User = get_user_model()
        user = User.objects.filter(phone_number=phone).first()
        if user is None:
            user = User.objects.create_user(phone_number=phone, password=PASSWORD, first_name=name.split()[0], is_supplier=True)
        seller, _ = InputSeller.objects.update_or_create(
            user=user,
            defaults={
                "seller_name": name, "business_name": name, "phone_number": phone,
                "seller_type": seller_type, "location": location, "region": region,
                "onboarding_completed": True, "is_active": True,
                "products_offered": ["fertilizer", "seeds", "pesticides"],
            },
        )
        return user, seller

    def handle(self, *args, **options):
        shop_user, shop = self._seller("0711000001", "Mama Neema Agrovet", "agro_input_dealer", "Moshi, Kilimanjaro", "Kilimanjaro")
        _, mfr = self._seller("0711000002", "Kilimo Bora Inputs Ltd", "manufacturer", "Arusha", "Arusha")

        for name, cat, pack, unit, wholesale, retail, moq, available in CATALOG:
            product, _ = WholesaleProduct.objects.get_or_create(
                manufacturer=mfr, name=name,
                defaults={
                    "category": cat, "pack_size": pack, "unit": unit, "wholesale_price": Decimal(wholesale),
                    "suggested_retail_price": Decimal(retail), "min_order_quantity": moq, "stock_available": available,
                    "description": f"{name}, {pack}. Demo product.",
                },
            )
            details = DETAILS.get(name, {})
            for field, value in details.items():
                setattr(product, field, value)
            product.registration_authority = WholesaleProduct.CATEGORY_REGULATOR.get(cat, "")
            product.save()

        # Give existing demo stock brands and expiry dates so the expiry alerts have something to show.
        today = timezone.localdate()
        for stock in ShopStockItem.objects.filter(shop=shop):
            if stock.wholesale_product_id and not stock.brand:
                stock.brand = stock.wholesale_product.brand
            if stock.category in ("seeds", "pesticides") and not stock.expiry_date:
                stock.expiry_date = today + timedelta(days=40 if "Tomato" in stock.name else 300)
                stock.batch_number = stock.batch_number or "DEMO-B-" + str(stock.pk).zfill(3)
            stock.save()

        if not ShopStockItem.objects.filter(shop=shop).exists():
            for name, cat, unit, cost, price, qty, reorder in [
                ("Jembe (hand hoe)", "tools", "piece", 7000, 9500, 14, 5),
                ("Knapsack Sprayer 16L", "tools", "piece", 45000, 58000, 3, 2),
                ("Tomato Seed Tanya 10g", "seeds", "packet", 3500, 5000, 40, 10),
            ]:
                item = ShopStockItem.objects.create(
                    shop=shop, name=name, category=cat, unit=unit, cost_price=Decimal(cost),
                    selling_price=Decimal(price), quantity=Decimal(qty), reorder_level=Decimal(reorder),
                )
                services.record_opening_stock(item, user=shop_user)

            urea = WholesaleProduct.objects.get(manufacturer=mfr, name="Urea 46% N")
            maize = WholesaleProduct.objects.get(manufacturer=mfr, name="Hybrid Maize Seed H614")
            received = services.create_purchase_order(shop, mfr, {urea.pk: 10, maize.pk: 40}, user=shop_user)
            services.manufacturer_update_order(received, "dispatched")
            services.receive_purchase_order(received, user=shop_user)
            services.create_purchase_order(shop, mfr, {urea.pk: 20}, user=shop_user, notes="Deliver before planting season")

            hoe = ShopStockItem.objects.get(shop=shop, name="Jembe (hand hoe)")
            maize_stock = ShopStockItem.objects.get(shop=shop, wholesale_product=maize)
            services.record_sale(shop, [{"stock_item": hoe.pk, "quantity": 2}, {"stock_item": maize_stock.pk, "quantity": 5}], user=shop_user)
            services.record_sale(shop, [{"stock_item": maize_stock.pk, "quantity": 3}], user=shop_user, payment_method="mobile_money")

        self.stdout.write(self.style.SUCCESS(
            f"Demo ready. Shop login 0711000001 / {PASSWORD}; manufacturer login 0711000002 / {PASSWORD}"
        ))

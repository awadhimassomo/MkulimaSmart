"""Tests for the mobile JSON API (/api/inputs/), authenticated with a real JWT like the Flutter app."""
from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PurchaseOrder, ShopStockItem, WholesaleProduct, WholesaleProductImage
from .tests import MEDIA, InputsTestBase, User, make_seller, png

API = "/api/inputs"


def jwt_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


PRODUCT = {
    "name": "DAP", "brand": "Kilimo Bora", "category": "fertilizer", "pack_size": "50 kg", "unit": "bag",
    "wholesale_price": "70000", "suggested_retail_price": "80000", "min_order_quantity": "1", "stock_available": "20",
    "composition": "18-46-0", "registration_number": "TFRA/F/1",
}


@override_settings(MEDIA_ROOT=MEDIA)
class ApiTestBase(InputsTestBase):
    def setUp(self):
        super().setUp()
        self.shop_api = jwt_client(self.shop_user)
        self.mfr_api = jwt_client(self.mfr_user)


class AuthAndProfileTests(ApiTestBase):
    def test_requires_jwt(self):
        self.assertEqual(APIClient().get(f"{API}/shop/stock/").status_code, 401)

    def test_options_lists_form_rules(self):
        data = self.shop_api.get(f"{API}/options/").json()
        self.assertIn({"value": "pesticides", "label": "Pesticides"}, data["categories"])
        self.assertEqual(data["product_form"]["required_by_category"]["pesticides"],
                         ["composition", "registration_number", "toxicity_class", "safety_precautions"])
        self.assertEqual(data["product_form"]["required_by_category"]["seeds"],
                         ["seed_variety", "registration_number", "suitable_regions", "soil_type"])
        self.assertEqual(data["category_regulator"]["seeds"], "tosci")
        self.assertIn({"value": "Kilimanjaro", "label": "Kilimanjaro"}, data["regions"])
        self.assertIn({"value": "loam", "label": "Loam (well-balanced)"}, data["soil_types"])

    def test_profile_required_then_created(self):
        user = User.objects.create_user(phone_number="0799000000", password="x" * 10)
        client = jwt_client(user)
        self.assertEqual(client.get(f"{API}/profile/").json(), {"profile": None, "role": None})

        response = client.get(f"{API}/shop/dashboard/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "profile_required")

        response = client.post(f"{API}/profile/", {"business_name": "New Agrovet"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("seller_type", response.json()["errors"])

        response = client.post(f"{API}/profile/", {
            "business_name": "New Agrovet", "location": "Dodoma", "seller_type": "agro_input_dealer",
            "products_offered": ["seeds", "fertilizer"],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("region", response.json()["errors"])

        response = client.post(f"{API}/profile/", {
            "business_name": "New Agrovet", "location": "Dodoma town", "region": "Dodoma", "seller_type": "agro_input_dealer",
            "products_offered": ["seeds", "fertilizer"],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["role"], "shop")
        self.assertTrue(response.json()["profile"]["list_on_kikapu"])  # opted in by default
        user.refresh_from_db()
        self.assertTrue(user.is_supplier)
        self.assertEqual(client.get(f"{API}/shop/dashboard/").status_code, 200)

    def test_wrong_role_rejected(self):
        response = self.shop_api.get(f"{API}/manufacturer/products/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "wrong_role")
        self.assertEqual(self.mfr_api.get(f"{API}/shop/stock/").status_code, 403)


class ManufacturerProductApiTests(ApiTestBase):
    def test_create_with_photos_and_field_errors(self):
        response = self.mfr_api.post(f"{API}/manufacturer/products/", {**PRODUCT, "brand": ""}, format="multipart")
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertIn("brand", errors)
        self.assertIn("images", errors)  # the web form's new_images is exposed as images

        response = self.mfr_api.post(
            f"{API}/manufacturer/products/",
            {**PRODUCT, "target_crops": ["Maize", "Beans"], "images": [png("a.png"), png("b.png")]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["registration_authority"], "tfra")
        self.assertEqual(data["target_crops"], ["Maize", "Beans"])
        self.assertTrue(data["is_active"])
        self.assertEqual(len(data["images"]), 2)
        self.assertTrue(data["cover_image"].startswith("http://testserver/media/"))
        self.assertEqual(data["wholesale_price"], 70000)  # JSON number, not a string

    def test_multipart_comma_separated_crops_like_dart_client(self):
        response = self.mfr_api.post(
            f"{API}/manufacturer/products/",
            {**PRODUCT, "target_crops": "Maize,Beans, maize", "images": [png()]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["target_crops"], ["Maize", "Beans"])

    def test_seed_requires_regions_and_soil_type_and_saves_them(self):
        seed = {
            "name": "Zamseed 606", "brand": "Zamseed", "category": "seeds", "pack_size": "2 kg", "unit": "packet",
            "wholesale_price": "9000", "min_order_quantity": "1", "stock_available": "20",
            "seed_variety": "606", "registration_number": "TOSCI/9",
        }
        response = self.mfr_api.post(f"{API}/manufacturer/products/", {**seed, "images": [png()]}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("suitable_regions", response.json()["errors"])
        self.assertIn("soil_type", response.json()["errors"])

        response = self.mfr_api.post(
            f"{API}/manufacturer/products/",
            {**seed, "suitable_regions": ["Kilimanjaro", "Arusha"], "soil_type": ["loam", "volcanic"], "images": [png()]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["suitable_regions"], ["Kilimanjaro", "Arusha"])
        self.assertEqual(data["soil_type"], ["loam", "volcanic"])
        self.assertEqual(data["soil_type_display"], "Loam (well-balanced), Volcanic / black cotton soil")

    def test_pesticide_rules_apply_to_api(self):
        response = self.mfr_api.post(
            f"{API}/manufacturer/products/", {**PRODUCT, "category": "pesticides", "images": [png()]}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["toxicity_class"], ["Required for Pesticides."])

    def test_patch_changes_only_sent_fields(self):
        WholesaleProductImage.objects.create(product=self.urea, image=png(), is_primary=True)
        self.urea.brand = "Yara"
        self.urea.composition = "46-0-0"
        self.urea.registration_number = "TFRA/1"
        self.urea.save()
        response = self.mfr_api.patch(f"{API}/manufacturer/products/{self.urea.pk}/", {"wholesale_price": 65000}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.urea.refresh_from_db()
        self.assertEqual(self.urea.wholesale_price, Decimal("65000"))
        self.assertEqual(self.urea.brand, "Yara")
        self.assertTrue(self.urea.is_active)

        response = self.mfr_api.patch(f"{API}/manufacturer/products/{self.urea.pk}/", {"is_active": False}, format="json")
        self.urea.refresh_from_db()
        self.assertFalse(self.urea.is_active)

    def test_image_management(self):
        first = WholesaleProductImage.objects.create(product=self.urea, image=png(), is_primary=True)
        response = self.mfr_api.delete(f"{API}/manufacturer/images/{first.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "last_photo")

        response = self.mfr_api.post(f"{API}/manufacturer/products/{self.urea.pk}/images/", {"images": [png()]}, format="multipart")
        self.assertEqual(response.status_code, 201)
        second = self.urea.images.exclude(pk=first.pk).get()
        self.mfr_api.post(f"{API}/manufacturer/images/{second.pk}/set-primary/")
        self.assertEqual(self.urea.images.get(is_primary=True), second)
        self.assertEqual(self.mfr_api.delete(f"{API}/manufacturer/images/{second.pk}/").status_code, 200)
        self.assertTrue(self.urea.images.get().is_primary)

    def test_cannot_touch_other_manufacturers_products(self):
        rival_user, _ = make_seller("0700000009", "manufacturer", "Rival")
        response = jwt_client(rival_user).patch(f"{API}/manufacturer/products/{self.urea.pk}/", {"wholesale_price": 1}, format="json")
        self.assertEqual(response.status_code, 404)


class ShopStockAndSalesApiTests(ApiTestBase):
    def test_stock_create_patch_adjust(self):
        response = self.shop_api.post(f"{API}/shop/stock/", {
            "name": "Tomato seed", "category": "seeds", "unit": "packet",
            "cost_price": 3000, "selling_price": 4500, "quantity": 20, "reorder_level": 5,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("expiry_date", response.json()["errors"])

        expiry = (timezone.localdate() + timedelta(days=30)).isoformat()
        response = self.shop_api.post(f"{API}/shop/stock/", {
            "name": "Tomato seed", "category": "seeds", "unit": "packet", "cost_price": 3000,
            "selling_price": 4500, "quantity": 20, "reorder_level": 5, "expiry_date": expiry, "batch_number": "B1",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        item = response.json()
        self.assertTrue(item["is_active"])
        self.assertTrue(item["expires_soon"])

        response = self.shop_api.patch(f"{API}/shop/stock/{item['id']}/", {"selling_price": 5000, "quantity": 999}, format="json")
        self.assertEqual(response.json()["selling_price"], 5000)
        self.assertEqual(response.json()["quantity"], 20)

        response = self.shop_api.post(f"{API}/shop/stock/{item['id']}/adjust/", {"change": -25}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.shop_api.post(f"{API}/shop/stock/{item['id']}/adjust/", {"change": -2, "note": "Damaged"}, format="json")
        self.assertEqual(response.json()["quantity"], 18)
        movements = self.shop_api.get(f"{API}/shop/stock/{item['id']}/movements/").json()["results"]
        self.assertEqual([m["reason"] for m in movements], ["adjustment", "opening"])

        listing = self.shop_api.get(f"{API}/shop/stock/?view=expiring").json()
        self.assertEqual([r["name"] for r in listing["results"]], ["Tomato seed"])

    def test_pos_checkout_and_sales_list(self):
        response = self.shop_api.post(f"{API}/shop/sales/", {
            "lines": [{"stock_item": self.item.pk, "quantity": 3}], "payment_method": "mobile_money", "amount_paid": 30000,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        sale = response.json()
        self.assertEqual(sale["total"], 30000)
        self.assertEqual(sale["items"][0]["product_name"], "Maize seed 2kg")

        response = self.shop_api.post(f"{API}/shop/sales/", {"lines": [{"stock_item": self.item.pk, "quantity": 100}]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Not enough stock", response.json()["message"])

        listing = self.shop_api.get(f"{API}/shop/sales/").json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["totals"], {"revenue": 30000, "sales": 1})
        self.assertEqual(self.shop_api.get(f"{API}/shop/sales/{sale['id']}/").json()["receipt_number"], sale["receipt_number"])

    def test_dashboard(self):
        data = self.shop_api.get(f"{API}/shop/dashboard/").json()
        self.assertEqual(data["stock"]["products"], 1)
        self.assertEqual(len(data["last_7_days"]), 7)


class OrderApiTests(ApiTestBase):
    def test_catalog_region_filter(self):
        WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="H614 Maize Seed", category="seeds", wholesale_price=9000,
            suitable_regions=["Kilimanjaro"], stock_available=50,
        )
        WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="Highland Bean Seed", category="seeds", wholesale_price=6000,
            suitable_regions=["Mbeya"], stock_available=50,
        )
        results = self.shop_api.get(f"{API}/shop/catalog/?region=Kilimanjaro").json()["results"]
        names = {p["name"] for p in results}
        self.assertIn("H614 Maize Seed", names)
        self.assertIn("Urea 46%", names)  # no region restriction set, matches any region
        self.assertNotIn("Highland Bean Seed", names)

    def test_multi_manufacturer_order_through_to_receipt(self):
        rival_user, rival = make_seller("0700000009", "manufacturer", "Rival Seeds")
        seed = WholesaleProduct.objects.create(
            manufacturer=rival, name="Bean seed", category="seeds", wholesale_price=5000, stock_available=50, brand="Mbegu",
        )
        self.urea.target_crops = ["Maize"]
        self.urea.save()

        catalog = self.shop_api.get(f"{API}/shop/catalog/?crop=maize").json()
        self.assertEqual([p["name"] for p in catalog["results"]], ["Urea 46%"])
        self.assertIs(catalog["results"][0]["in_my_stock"], False)

        response = self.shop_api.post(f"{API}/shop/orders/", {
            "items": [{"product": self.urea.pk, "quantity": 2}], "notes": "",
        }, format="json")
        self.assertEqual(response.status_code, 400)  # below the minimum order of 5
        self.assertFalse(PurchaseOrder.objects.exists())

        response = self.shop_api.post(f"{API}/shop/orders/", {
            "items": [{"product": self.urea.pk, "quantity": 5}, {"product": seed.pk, "quantity": 10}], "notes": "Deliver Monday",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        orders = response.json()["orders"]
        self.assertEqual(len(orders), 2)
        self.assertTrue(all(o["allowed_actions"] == ["cancel"] for o in orders))
        urea_order = next(o for o in orders if o["manufacturer"]["id"] == self.mfr.pk)

        mfr_view = self.mfr_api.get(f"{API}/manufacturer/orders/{urea_order['id']}/").json()
        self.assertEqual(mfr_view["allowed_actions"], ["confirmed", "dispatched", "cancelled"])
        self.assertEqual(self.mfr_api.get(f"{API}/manufacturer/orders/").json()["count"], 1)  # only its own order

        response = self.mfr_api.post(f"{API}/manufacturer/orders/{urea_order['id']}/status/", {"status": "dispatched", "note": "Truck T123"}, format="json")
        self.assertEqual(response.json()["status"], "dispatched")
        self.assertEqual(self.shop_api.get(f"{API}/shop/orders/{urea_order['id']}/").json()["allowed_actions"], ["receive"])

        response = self.shop_api.post(f"{API}/shop/orders/{urea_order['id']}/receive/")
        self.assertEqual(response.json()["status"], "received")
        self.assertTrue(ShopStockItem.objects.filter(shop=self.shop, wholesale_product=self.urea, quantity=5).exists())
        self.assertIs(self.shop_api.get(f"{API}/shop/catalog/{self.urea.pk}/").json()["in_my_stock"], True)

        # The rival cannot act on the other manufacturer's order.
        self.assertEqual(jwt_client(rival_user).post(f"{API}/manufacturer/orders/{urea_order['id']}/status/", {"status": "cancelled"}, format="json").status_code, 404)

    def test_manufacturer_dashboard(self):
        data = self.mfr_api.get(f"{API}/manufacturer/dashboard/").json()
        self.assertEqual(data["products_listed"], 1)
        self.assertEqual(data["pending_orders"], 0)

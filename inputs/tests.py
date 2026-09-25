import io
import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image

from operations.models import InputSeller

from . import services
from .forms import ShopStockItemForm, WholesaleProductForm
from .models import PurchaseOrder, Sale, ShopStockItem, StockMovement, WholesaleProduct, WholesaleProductImage

User = get_user_model()
MEDIA = tempfile.mkdtemp()


def png(name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def make_seller(phone, seller_type, name):
    user = User.objects.create_user(phone_number=phone, password="pass12345", is_supplier=True)
    seller = InputSeller.objects.create(
        user=user, seller_name=name, business_name=name, phone_number=phone,
        seller_type=seller_type, location="Arusha", onboarding_completed=True,
    )
    return user, seller


@override_settings(MEDIA_ROOT=MEDIA)
class InputsTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        # settings.LANGUAGE_CODE is "en-us", which is not in LANGUAGES, so reverse() would build
        # /en-us/ URLs (404) until some request activates a supported language.
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.shop_user, self.shop = make_seller("0700000001", "agro_input_dealer", "Mama Agro Shop")
        self.mfr_user, self.mfr = make_seller("0700000002", "manufacturer", "Kilimo Fertilizers Ltd")
        self.urea = WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="Urea 46%", category="fertilizer", pack_size="50 kg", unit="bag",
            wholesale_price=Decimal("60000"), suggested_retail_price=Decimal("72000"), min_order_quantity=5, stock_available=100,
        )
        self.item = ShopStockItem.objects.create(
            shop=self.shop, name="Maize seed 2kg", category="seeds", unit="packet",
            cost_price=Decimal("8000"), selling_price=Decimal("10000"), quantity=Decimal("10"),
        )


class SaleServiceTests(InputsTestBase):
    def test_sale_deducts_stock_and_records_movement(self):
        sale = services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 3}], user=self.shop_user, amount_paid=40000)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("7"))
        self.assertEqual(sale.total, Decimal("30000"))
        self.assertEqual(sale.change_due, Decimal("10000"))
        movement = StockMovement.objects.get(stock_item=self.item, reason="sale")
        self.assertEqual(movement.change, Decimal("-3"))
        self.assertEqual(movement.reference, sale.receipt_number)

    def test_cannot_oversell(self):
        with self.assertRaises(services.StockError):
            services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 11}])
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("10"))
        self.assertFalse(Sale.objects.exists())

    def test_duplicate_lines_are_merged_before_stock_check(self):
        with self.assertRaises(services.StockError):
            services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 6}, {"stock_item": self.item.pk, "quantity": 6}])

    def test_underpayment_requires_credit(self):
        with self.assertRaises(services.StockError):
            services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 1}], amount_paid=5000)
        sale = services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 1}], amount_paid=5000, payment_method="credit")
        self.assertEqual(sale.balance_due, Decimal("5000"))

    def test_cannot_sell_other_shops_stock(self):
        _, other = make_seller("0700000003", "agro_input_dealer", "Other Shop")
        with self.assertRaises(services.StockError):
            services.record_sale(other, [{"stock_item": self.item.pk, "quantity": 1}])

    def test_prefilled_country_code_is_not_stored_as_customer_phone(self):
        sale = services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 1}], customer_phone="+255")
        self.assertEqual(sale.customer_phone, "")

    def test_discount_cannot_exceed_subtotal(self):
        with self.assertRaises(services.StockError):
            services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 1}], discount=20000)


class PurchaseOrderFlowTests(InputsTestBase):
    def test_full_order_lifecycle_adds_stock_with_catalog_photo(self):
        WholesaleProductImage.objects.create(product=self.urea, image=png(), is_primary=True)
        order = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 10}, user=self.shop_user)
        self.assertEqual(order.total, Decimal("600000"))

        services.manufacturer_update_order(order, "confirmed")
        services.manufacturer_update_order(order, "dispatched")
        self.urea.refresh_from_db()
        self.assertEqual(self.urea.stock_available, 90)

        services.receive_purchase_order(order, user=self.shop_user)
        order.refresh_from_db()
        self.assertEqual(order.status, "received")
        stock = ShopStockItem.objects.get(shop=self.shop, wholesale_product=self.urea)
        self.assertEqual(stock.quantity, Decimal("10"))
        self.assertEqual(stock.cost_price, Decimal("60000"))
        self.assertEqual(stock.selling_price, Decimal("72000"))
        self.assertTrue(stock.image)

        # A second delivery tops up the same stock line.
        order2 = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 5})
        services.manufacturer_update_order(order2, "dispatched")
        services.receive_purchase_order(order2)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("15"))
        self.assertEqual(ShopStockItem.objects.filter(shop=self.shop, wholesale_product=self.urea).count(), 1)

    def test_min_order_quantity_enforced(self):
        with self.assertRaises(services.StockError):
            services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 2})

    def test_cannot_dispatch_more_than_available(self):
        order = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 100})
        self.urea.stock_available = 50
        self.urea.save()
        with self.assertRaises(services.StockError):
            services.manufacturer_update_order(order, "dispatched")
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")

    def test_cannot_receive_before_dispatch(self):
        order = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 5})
        with self.assertRaises(services.StockError):
            services.receive_purchase_order(order)

    def test_shop_can_only_cancel_pending(self):
        order = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 5})
        services.manufacturer_update_order(order, "confirmed")
        with self.assertRaises(services.StockError):
            services.shop_cancel_order(order)


class ViewTests(InputsTestBase):
    def test_role_routing(self):
        self.client.force_login(self.shop_user)
        self.assertRedirects(self.client.get(reverse("inputs:home")), reverse("inputs:shop_dashboard"))
        self.assertRedirects(self.client.get(reverse("inputs:manufacturer_dashboard")), reverse("inputs:home"), target_status_code=302)
        self.client.force_login(self.mfr_user)
        self.assertRedirects(self.client.get(reverse("inputs:home")), reverse("inputs:manufacturer_dashboard"))

    def test_shop_pages_render(self):
        self.client.force_login(self.shop_user)
        services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 1}])
        for name in ["shop_dashboard", "pos", "sale_list", "stock_list", "stock_create", "catalog", "order_cart", "order_list"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"inputs:{name}")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inputs:catalog_product", args=[self.urea.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("inputs:stock_edit", args=[self.item.pk])).status_code, 200)

    def test_catalog_product_page_shows_region_and_soil_suitability(self):
        seed = WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="H614 Maize Seed", category="seeds", wholesale_price=9000,
            suitable_regions=["Kilimanjaro", "Arusha"], soil_type=["loam", "volcanic"], stock_available=50,
        )
        self.client.force_login(self.shop_user)
        response = self.client.get(reverse("inputs:catalog_product", args=[seed.pk]))
        self.assertContains(response, "Kilimanjaro, Arusha")
        self.assertContains(response, "Loam (well-balanced), Volcanic / black cotton soil")

    def test_manufacturer_product_form_shows_region_and_soil_fields(self):
        self.client.force_login(self.mfr_user)
        response = self.client.get(reverse("inputs:manufacturer_product_create"))
        self.assertContains(response, "Suitable regions")
        self.assertContains(response, "Suitable soil type")
        self.assertContains(response, "Kilimanjaro")

    def test_manufacturer_pages_render(self):
        self.client.force_login(self.mfr_user)
        order = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 5})
        for url in [
            reverse("inputs:manufacturer_dashboard"),
            reverse("inputs:manufacturer_products"),
            reverse("inputs:manufacturer_product_create"),
            reverse("inputs:manufacturer_product_edit", args=[self.urea.pk]),
            reverse("inputs:manufacturer_orders"),
            reverse("inputs:manufacturer_order_detail", args=[order.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pos_checkout_endpoint(self):
        self.client.force_login(self.shop_user)
        response = self.client.post(
            reverse("inputs:pos_checkout"),
            data=json.dumps({"lines": [{"stock_item": self.item.pk, "quantity": 2}], "payment_method": "mobile_money"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("8"))

        response = self.client.post(
            reverse("inputs:pos_checkout"),
            data=json.dumps({"lines": [{"stock_item": self.item.pk, "quantity": 99}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Not enough stock", response.json()["error"])

    def test_manufacturer_uploads_multiple_images(self):
        self.client.force_login(self.mfr_user)
        response = self.client.post(reverse("inputs:manufacturer_product_create"), {
            "name": "DAP", "brand": "Kilimo Bora", "category": "fertilizer", "pack_size": "50 kg", "unit": "bag",
            "composition": "18-46-0", "registration_number": "TFRA/F/0231", "target_crops": "Maize, beans, Maize",
            "wholesale_price": "70000", "suggested_retail_price": "80000", "min_order_quantity": "1",
            "stock_available": "20", "description": "", "is_active": "on",
            "new_images": [png("a.png"), png("b.png")],
        })
        product = WholesaleProduct.objects.get(name="DAP")
        self.assertEqual(product.registration_authority, "tfra")
        self.assertEqual(product.target_crops, ["Maize", "beans"])
        self.assertRedirects(response, reverse("inputs:manufacturer_product_edit", args=[product.pk]))
        self.assertEqual(product.images.count(), 2)
        self.assertEqual(product.images.filter(is_primary=True).count(), 1)

        second = product.images.filter(is_primary=False).first()
        self.client.post(reverse("inputs:manufacturer_image_action", args=[second.pk]), {"action": "primary"})
        self.assertEqual(product.images.get(is_primary=True), second)

        self.client.post(reverse("inputs:manufacturer_image_action", args=[second.pk]), {"action": "delete"})
        self.assertEqual(product.images.count(), 1)
        last = product.images.get()
        self.assertTrue(last.is_primary)

        # The last photo cannot be removed.
        self.client.post(reverse("inputs:manufacturer_image_action", args=[last.pk]), {"action": "delete"})
        self.assertEqual(product.images.count(), 1)

    def test_manufacturer_cannot_touch_other_manufacturers_images(self):
        other_user, _ = make_seller("0700000009", "manufacturer", "Rival Ltd")
        image = WholesaleProductImage.objects.create(product=self.urea, image=png(), is_primary=True)
        self.client.force_login(other_user)
        response = self.client.post(reverse("inputs:manufacturer_image_action", args=[image.pk]), {"action": "delete"})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WholesaleProductImage.objects.filter(pk=image.pk).exists())

    def test_order_via_cart_and_receive(self):
        self.client.force_login(self.shop_user)
        self.client.post(reverse("inputs:order_cart_update"), {"product": self.urea.pk, "quantity": 5})
        response = self.client.post(reverse("inputs:order_submit", args=[self.mfr.pk]), {"notes": "Deliver Monday"})
        order = PurchaseOrder.objects.get()
        self.assertRedirects(response, reverse("inputs:order_detail", args=[order.pk]))
        self.assertEqual(order.notes, "Deliver Monday")
        self.assertEqual(self.client.session.get("inputs_order_cart"), {})

        self.client.force_login(self.mfr_user)
        self.client.post(reverse("inputs:manufacturer_order_detail", args=[order.pk]), {"status": "dispatched"})
        self.client.force_login(self.shop_user)
        self.client.post(reverse("inputs:order_action", args=[order.pk]), {"action": "receive"})
        self.assertTrue(ShopStockItem.objects.filter(shop=self.shop, wholesale_product=self.urea, quantity=5).exists())

    def test_stock_edit_does_not_change_quantity_directly(self):
        self.client.force_login(self.shop_user)
        self.client.post(reverse("inputs:stock_edit", args=[self.item.pk]), {
            "name": "Maize seed 2kg", "category": "seeds", "sku": "", "unit": "packet",
            "cost_price": "8000", "selling_price": "11000", "reorder_level": "5", "is_active": "on", "quantity": "999",
            "expiry_date": (timezone.localdate() + timedelta(days=200)).isoformat(),
        })
        self.item.refresh_from_db()
        self.assertEqual(self.item.selling_price, Decimal("11000"))
        self.assertEqual(self.item.quantity, Decimal("10"))


class EntryPointTests(InputsTestBase):
    def test_supplier_login_lands_on_input_dashboard(self):
        response = self.client.post(reverse("website:login"), {"username": "0700000001", "password": "pass12345"})
        self.assertRedirects(response, reverse("inputs:home"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("inputs:home")), reverse("inputs:shop_dashboard"))

    def test_header_dashboard_link_points_to_input_dashboard(self):
        self.client.force_login(self.mfr_user)
        html = self.client.get(reverse("inputs:manufacturer_dashboard")).content.decode()
        self.assertIn(f'href="{reverse("inputs:home")}"', html)

    def test_old_page_is_still_reachable_as_marketplace_listings(self):
        self.client.force_login(self.shop_user)
        response = self.client.get(reverse("marketplace:supplier_dashboard"))
        self.assertContains(response, "Marketplace Listings")
        self.assertContains(response, "Back to My Dashboard")


class ProductFormRuleTests(InputsTestBase):
    BASE = {
        "name": "Test input", "brand": "Brand", "pack_size": "1 litre", "unit": "bottle",
        "wholesale_price": "10000", "min_order_quantity": "1", "stock_available": "10", "is_active": "on",
    }

    def form(self, category, **extra):
        data = {**self.BASE, "category": category, **extra}
        return WholesaleProductForm(data=data, files={"new_images": [png()]} if extra.pop("_photo", True) else {})

    def test_always_required_fields(self):
        form = WholesaleProductForm(data={"category": "tools"}, files={"new_images": [png()]})
        self.assertFalse(form.is_valid())
        for name in ["name", "brand", "pack_size", "wholesale_price", "stock_available"]:
            self.assertIn(name, form.errors)

    def test_photo_required_on_create(self):
        form = WholesaleProductForm(data={**self.BASE, "category": "tools"})
        self.assertFalse(form.is_valid())
        self.assertIn("new_images", form.errors)

    def test_pesticide_requires_safety_fields(self):
        form = self.form("pesticides")
        self.assertFalse(form.is_valid())
        for name in ["composition", "registration_number", "toxicity_class", "safety_precautions"]:
            self.assertIn(name, form.errors)

        form = self.form(
            "pesticides", composition="Lambda-cyhalothrin 5% EC", registration_number="TPHPA/123",
            toxicity_class="II", safety_precautions="Wear gloves.",
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["registration_authority"], "tphpa")

    def test_seed_requires_variety_and_registration(self):
        form = self.form("seeds")
        self.assertFalse(form.is_valid())
        self.assertIn("seed_variety", form.errors)
        self.assertIn("registration_number", form.errors)
        self.assertIn("suitable_regions", form.errors)
        self.assertIn("soil_type", form.errors)

    def test_seed_accepts_regions_and_soil_type_and_saves_them(self):
        form = self.form(
            "seeds", seed_variety="H614", registration_number="TOSCI/1",
            suitable_regions=["Kilimanjaro", "Arusha"], soil_type=["loam", "volcanic"],
        )
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        self.assertEqual(product.suitable_regions, ["Kilimanjaro", "Arusha"])
        self.assertEqual(product.soil_type, ["loam", "volcanic"])
        self.assertEqual(product.suitable_regions_display, "Kilimanjaro, Arusha")
        self.assertEqual(product.soil_type_display, "Loam (well-balanced), Volcanic / black cotton soil")

    def test_seedlings_also_require_regions_and_soil_type(self):
        form = self.form("seedlings", seed_variety="Avocado grafted")
        self.assertFalse(form.is_valid())
        self.assertIn("suitable_regions", form.errors)
        self.assertIn("soil_type", form.errors)

    def test_unknown_region_value_rejected(self):
        form = self.form(
            "seeds", seed_variety="H614", registration_number="TOSCI/1",
            suitable_regions=["Narnia"], soil_type=["loam"],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("suitable_regions", form.errors)

    def test_regions_and_soil_type_optional_but_kept_for_other_categories(self):
        # Not required for fertilizer, but a manufacturer may still specify them
        # (e.g. "this fertilizer suits acidic, volcanic soils"), and it is not cleared.
        form = self.form(
            "fertilizer", composition="18-46-0", registration_number="TFRA/1",
            suitable_regions=["Mbeya"], soil_type=["volcanic"],
        )
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        self.assertEqual(product.suitable_regions, ["Mbeya"])
        self.assertEqual(product.soil_type, ["volcanic"])

    def test_tools_need_no_regulatory_fields_and_drop_irrelevant_values(self):
        form = self.form("tools", toxicity_class="II", seed_variety="H614", germination_rate="90")
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        self.assertEqual(product.toxicity_class, "")
        self.assertEqual(product.seed_variety, "")
        self.assertIsNone(product.germination_rate)

    def test_germination_rate_capped_at_100(self):
        form = self.form("seeds", seed_variety="H614", registration_number="TOSCI/1", germination_rate="120")
        self.assertFalse(form.is_valid())
        self.assertIn("germination_rate", form.errors)


class StockExpiryTests(InputsTestBase):
    def test_expiry_required_for_seeds_and_pesticides(self):
        data = {"name": "Seed", "category": "seeds", "unit": "packet", "cost_price": "1", "selling_price": "2",
                "quantity": "1", "reorder_level": "1", "is_active": "on"}
        self.assertIn("expiry_date", ShopStockItemForm(data=data).errors)
        self.assertTrue(ShopStockItemForm(data={**data, "category": "tools"}).is_valid())

    def test_selling_below_cost_rejected(self):
        data = {"name": "Hoe", "category": "tools", "unit": "piece", "cost_price": "100", "selling_price": "90",
                "quantity": "1", "reorder_level": "1"}
        self.assertIn("selling_price", ShopStockItemForm(data=data).errors)

    def test_expiring_items_on_dashboard_and_stock_filter(self):
        self.item.expiry_date = timezone.localdate() + timedelta(days=10)
        self.item.save()
        self.client.force_login(self.shop_user)
        response = self.client.get(reverse("inputs:shop_dashboard"))
        self.assertEqual(response.context["expiring_count"], 1)
        response = self.client.get(reverse("inputs:stock_list") + "?view=expiring")
        self.assertEqual(list(response.context["items"]), [self.item])

    def test_received_stock_inherits_brand(self):
        self.urea.brand = "Yara"
        self.urea.save()
        order = services.create_purchase_order(self.shop, self.mfr, {self.urea.pk: 5})
        services.manufacturer_update_order(order, "dispatched")
        services.receive_purchase_order(order)
        self.assertEqual(ShopStockItem.objects.get(wholesale_product=self.urea).brand, "Yara")


class CatalogFilterTests(InputsTestBase):
    def test_filter_by_crop_and_brand_search(self):
        self.urea.target_crops = ["Maize", "Rice"]
        self.urea.brand = "Yara"
        self.urea.save()
        WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="Coffee booster", category="fertilizer", wholesale_price=1,
            target_crops=["Coffee"], stock_available=5,
        )
        self.client.force_login(self.shop_user)
        page = self.client.get(reverse("inputs:catalog") + "?crop=maize").context["page_obj"]
        self.assertEqual([p.name for p in page], ["Urea 46%"])
        page = self.client.get(reverse("inputs:catalog") + "?q=yara").context["page_obj"]
        self.assertEqual([p.name for p in page], ["Urea 46%"])

    def test_filter_by_region_also_includes_products_with_no_region_set(self):
        # self.urea has no suitable_regions set: it should still show up for any region filter.
        kilimanjaro_only = WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="H614 Maize Seed", category="seeds", wholesale_price=9000,
            suitable_regions=["Kilimanjaro"], stock_available=50,
        )
        mbeya_only = WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="Highland Bean Seed", category="seeds", wholesale_price=6000,
            suitable_regions=["Mbeya"], stock_available=50,
        )
        self.client.force_login(self.shop_user)
        page = self.client.get(reverse("inputs:catalog") + "?region=Kilimanjaro").context["page_obj"]
        names = {p.name for p in page}
        self.assertIn("H614 Maize Seed", names)
        self.assertIn("Urea 46%", names)  # no region restriction, matches any region search
        self.assertNotIn("Highland Bean Seed", names)

    def test_web_catalog_defaults_to_shops_own_region(self):
        self.shop.region = "Kilimanjaro"
        self.shop.save()
        WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="H614 Maize Seed", category="seeds", wholesale_price=9000,
            suitable_regions=["Kilimanjaro"], stock_available=50,
        )
        WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="Highland Bean Seed", category="seeds", wholesale_price=6000,
            suitable_regions=["Mbeya"], stock_available=50,
        )
        self.client.force_login(self.shop_user)
        response = self.client.get(reverse("inputs:catalog"))
        self.assertEqual(response.context["filters"]["region"], "Kilimanjaro")
        names = {p.name for p in response.context["page_obj"]}
        self.assertNotIn("Highland Bean Seed", names)

        # Explicitly clearing the region shows everything, overriding the default.
        response = self.client.get(reverse("inputs:catalog") + "?region=")
        names = {p.name for p in response.context["page_obj"]}
        self.assertIn("Highland Bean Seed", names)


class CatalogProductFarmerTalkTests(InputsTestBase):
    def setUp(self):
        super().setUp()
        from community.models import Discussion
        self.farmer_user = User.objects.create_user(phone_number="0700000099", password="pass12345", is_farmer=True)
        self.zamseed = WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="Zamseed 606 Maize Seed", category="seeds", pack_size="2 kg",
            unit="packet", wholesale_price=Decimal("9000"), seed_variety="Zamseed 606", target_crops=["Maize"],
        )
        self.discussion = Discussion.objects.create(
            author=self.farmer_user, crop="Maize", seed_variety="Zamseed 606",
            title="Zamseed 606 on 1 acre, 145 debe", body="Planted 3 packets.",
        )

    def test_matching_discussion_shown_on_catalog_product_page(self):
        self.client.force_login(self.shop_user)
        response = self.client.get(reverse("inputs:catalog_product", args=[self.zamseed.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.discussion, list(response.context["farmer_discussions"]))
        self.assertContains(response, "Farmer Talk")
        self.assertContains(response, "145 debe")

    def test_unrelated_product_shows_no_discussions(self):
        self.client.force_login(self.shop_user)
        response = self.client.get(reverse("inputs:catalog_product", args=[self.urea.pk]))
        self.assertEqual(list(response.context["farmer_discussions"]), [])

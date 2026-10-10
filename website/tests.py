from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from community.models import Discussion
from website.models import Category, Product

User = get_user_model()


class ProductDetailFarmerTalkTests(TestCase):
    """settings.LANGUAGE_CODE ('en-us') is not in LANGUAGES, so reverse() would 404 until
    a supported language is activated; see the same workaround in community/tests.py."""

    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)

        self.supplier = User.objects.create_user(phone_number="0700000020", password="pass12345", is_supplier=True)
        # website/migrations/0006_seed_supplier_categories.py already seeds a "Seeds" category
        # with slug "seeds", so this test uses its own category to avoid a slug collision.
        self.category = Category.objects.create(name="Test Seeds", slug="test-seeds")
        self.product = Product.objects.create(
            name="Hybrid Maize Seed H614", slug="hybrid-maize-seed-h614", category=self.category,
            description="High-yield hybrid maize.", price=12000, supplier=self.supplier,
        )
        self.farmer = User.objects.create_user(phone_number="0700000021", password="pass12345", is_farmer=True)

    def test_matching_discussion_shown_on_product_page(self):
        discussion = Discussion.objects.create(
            author=self.farmer, crop="Maize", seed_variety="H614",
            title="H614 on 1 acre, 145 debe", body="Planted 3 packets.",
        )
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn(discussion, list(response.context["farmer_discussions"]))
        self.assertContains(response, "Farmer Talk")
        self.assertContains(response, "H614 on 1 acre, 145 debe")

    def test_unrelated_discussion_not_shown(self):
        Discussion.objects.create(author=self.farmer, crop="Beans", title="Beans notes", body="x")
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(list(response.context["farmer_discussions"]), [])

    def test_share_link_prefills_crop_with_product_name(self):
        response = self.client.get(self.product.get_absolute_url())
        expected = reverse("community:discussion_create")
        self.assertContains(response, f'{expected}?crop=Hybrid')


class PriceFormattingTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)

    def test_the_tzs_filter(self):
        from decimal import Decimal

        from website.templatetags.money import tzs

        self.assertEqual(tzs(Decimal("18000.00")), "18,000")
        self.assertEqual(tzs(18000), "18,000")
        self.assertEqual(tzs(18000.0), "18,000")
        self.assertEqual(tzs("1234567"), "1,234,567")
        self.assertEqual(tzs(Decimal("18000.50")), "18,000.50")
        self.assertEqual(tzs(0), "0")
        self.assertEqual(tzs(Decimal("999")), "999")
        self.assertEqual(tzs(None), "")
        self.assertEqual(tzs(""), "")
        self.assertEqual(tzs("not a price"), "not a price")

    def test_product_and_category_pages_show_formatted_prices(self):
        supplier = User.objects.create_user(phone_number="0700000030", password="pass12345", is_supplier=True)
        category = Category.objects.create(name="Test Fertilizer", slug="test-fertilizer")
        product = Product.objects.create(
            name="CAN Fertilizer 50kg", slug="can-fertilizer-50kg", category=category, description="Top dressing.",
            price=125000, discount_price=118500, stock=10, supplier=supplier,
        )
        detail = self.client.get(product.get_absolute_url())
        self.assertContains(detail, "TSh 125,000")
        self.assertContains(detail, "TSh 118,500")
        self.assertNotContains(detail, "125000.00")
        self.assertNotContains(detail, "TSh 125000")
        listing = self.client.get(category.get_absolute_url())
        self.assertContains(listing, "TSh 125,000")
        self.assertNotContains(listing, "125000.00")

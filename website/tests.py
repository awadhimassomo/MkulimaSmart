from unittest import mock

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


class UserAdminTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.admin = User.objects.create_superuser(password="pass12345", email="admin@mkulima.test")
        self.client.force_login(self.admin)
        self.person = User.objects.create_user(password="old-pass-123", email="neema@zamseed.test", first_name="Neema")

    def test_the_account_page_offers_a_password_change_form(self):
        page = self.client.get(reverse("admin:website_user_change", args=[self.person.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Reset password")
        self.assertContains(page, "../password/")
        self.assertNotContains(page, "pbkdf2_sha256$")  # the hash is no longer an editable text box

    def test_an_administrator_can_set_a_new_password(self):
        url = reverse("admin:auth_user_password_change", args=[self.person.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        response = self.client.post(url, {"password1": "Brand-new-pass-77", "password2": "Brand-new-pass-77"})
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("Brand-new-pass-77"))

    def test_a_new_account_made_in_the_admin_has_a_hashed_password_and_can_sign_in(self):
        response = self.client.post(reverse("admin:website_user_add"), {
            "email": "New.Person@Zamseed.test", "phone_number": "", "first_name": "New", "last_name": "Person",
            "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99",
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        created = User.objects.get(email="new.person@zamseed.test")
        self.assertTrue(created.check_password("Str0ng-pass-99"))
        self.assertNotEqual(created.password, "Str0ng-pass-99")
        self.assertIsNone(created.phone_number)

    def test_mismatched_or_weak_passwords_are_refused(self):
        base = {"email": "x@y.test", "phone_number": "", "first_name": "X", "last_name": "Y"}
        mismatch = self.client.post(reverse("admin:website_user_add"), {**base, "password1": "Str0ng-pass-99", "password2": "other"})
        self.assertEqual(mismatch.status_code, 200)
        weak = self.client.post(reverse("admin:website_user_add"), {**base, "password1": "12345678", "password2": "12345678"})
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(User.objects.filter(email="x@y.test").exists())


class ForgotPasswordTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.person = User.objects.create_user(password="old-pass-123", email="neema@zamseed.test")

    def test_the_forgot_password_page_emails_a_working_link(self):
        from django.core import mail

        response = self.client.post(reverse("website:password_reset"), {"email": "neema@zamseed.test"})
        self.assertRedirects(response, reverse("website:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["neema@zamseed.test"])
        link = next(word for word in mail.outbox[0].body.split() if "/reset/" in word)
        opened = self.client.get(link.replace("http://testserver", ""), follow=True)
        form_url = opened.redirect_chain[-1][0]
        self.client.post(form_url, {"new_password1": "Brand-new-pass-77", "new_password2": "Brand-new-pass-77"})
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("Brand-new-pass-77"))

    def test_an_unknown_email_looks_the_same_and_sends_nothing(self):
        from django.core import mail

        response = self.client.post(reverse("website:password_reset"), {"email": "nobody@nowhere.test"})
        self.assertRedirects(response, reverse("website:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_a_broken_mail_server_does_not_crash_the_page(self):
        with mock.patch("django.contrib.auth.forms.PasswordResetForm.send_mail", side_effect=OSError("down")):
            response = self.client.post(reverse("website:password_reset"), {"email": "neema@zamseed.test"})
        self.assertRedirects(response, reverse("website:password_reset_done"))


class FooterLinksTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)

    def test_the_footer_links_to_the_government_app_and_the_operations_dashboard(self):
        page = self.client.get(reverse("website:home"))
        self.assertContains(page, f'href="{reverse("gova_pp:login")}"')
        self.assertContains(page, f'href="{reverse("ops:overview")}"')

    def test_the_operations_link_sends_visitors_to_sign_in_and_only_administrators_in(self):
        self.assertRedirects(self.client.get(reverse("ops:overview")), reverse("gova_pp:login"), fetch_redirect_response=False)
        admin = User.objects.create_superuser(password="pass12345", email="admin@mkulima.test")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("ops:overview")).status_code, 200)


class ListingVisibilityTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.category = Category.objects.create(name="Visibility Seeds", slug="visibility-seeds")
        self.sellers = []
        for i in range(6):
            seller = User.objects.create_user(phone_number=f"07100000{i:02d}", password="pass12345", is_supplier=True, address="Mbeya town" if i == 0 else "Arusha")
            self.sellers.append(seller)

    def product(self, seller, name, **fields):
        fields.setdefault("price", 5000)
        fields.setdefault("stock", 3)
        return Product.objects.create(
            name=name, slug=name.lower().replace(" ", "-"), category=self.category, description="Seed.", supplier=seller, **fields,
        )

    def test_newest_listings_show_on_the_home_page_not_just_the_oldest(self):
        names = [f"Listing number {i}" for i in range(6)]
        for seller, name in zip(self.sellers, names):
            self.product(seller, name)
        page = self.client.get(reverse("website:home"))
        shown = [p.name for p in page.context["featured_products"]]
        self.assertEqual(shown, ["Listing number 5", "Listing number 4", "Listing number 3", "Listing number 2"])

    def test_the_marketplace_grid_hides_switched_off_listings_so_no_link_leads_to_a_404(self):
        live = self.product(self.sellers[0], "Live listing")
        off = self.product(self.sellers[1], "Switched off listing", is_active=False)
        page = self.client.get(reverse("website:marketplace"))
        self.assertContains(page, live.name)
        self.assertNotContains(page, off.name)
        self.assertEqual(self.client.get(off.get_absolute_url()).status_code, 404)

    def test_the_region_filter_works_and_does_not_crash(self):
        self.product(self.sellers[0], "Mbeya seed")
        self.product(self.sellers[1], "Arusha seed")
        page = self.client.get(reverse("website:marketplace"), {"region": "Mbeya"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Mbeya seed")
        self.assertNotContains(page, "Arusha seed")

    def test_paging_links_keep_the_filters(self):
        for i in range(14):
            self.product(self.sellers[i % 6], f"Filtered item {i}", price=1000 + i)
        page = self.client.get(reverse("website:marketplace"), {"category": self.category.pk, "order": "price"})
        self.assertContains(page, f"?page=2&category={self.category.pk}&amp;order=price")

    def test_the_marketplace_app_page_also_hides_switched_off_listings(self):
        self.product(self.sellers[0], "Live listing")
        self.product(self.sellers[1], "Switched off listing", is_active=False)
        page = self.client.get(reverse("marketplace:home"))
        self.assertContains(page, "Live listing")
        self.assertNotContains(page, "Switched off listing")


class BrandBackfillAndNavTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.category = Category.objects.create(name="Backfill Seeds", slug="backfill-seeds")
        self.seller = User.objects.create_user(phone_number="0700000090", password="pass12345", is_supplier=True)

    def product(self, name, description, brand=""):
        return Product.objects.create(name=name, slug=name.lower().replace(" ", "-"), category=self.category, description=description,
                                      price=3500, stock=5, supplier=self.seller, brand=brand)

    def run_migration(self):
        import importlib

        from django.apps import apps

        module = importlib.import_module("website.migrations.0010_backfill_brand_from_description")
        module.move_brand_out_of_the_description(apps, None)

    def test_a_brand_written_into_the_description_moves_into_the_brand_field(self):
        old = self.product("Mahindi", "Brand: STAHA\n\nPack size: 1 kg\nSuitable crops: Maize")
        self.run_migration()
        old.refresh_from_db()
        self.assertEqual(old.brand, "STAHA")
        self.assertEqual(old.description, "Pack size: 1 kg\nSuitable crops: Maize")

    def test_brands_with_commas_and_digits_are_kept_whole(self):
        old = self.product("Mtama", "Brand: 1,MACIA\n\nPack size: 500 g")
        self.run_migration()
        old.refresh_from_db()
        self.assertEqual(old.brand, "1,MACIA")

    def test_a_description_that_was_only_the_brand_falls_back_to_the_name(self):
        old = self.product("Alizeti (sunflower)", "Brand: Record")
        self.run_migration()
        old.refresh_from_db()
        self.assertEqual((old.brand, old.description), ("Record", "Alizeti (sunflower)"))

    def test_listings_that_already_have_a_brand_or_no_brand_line_are_left_alone(self):
        keep = self.product("Kept", "Brand: Other\n\nText", brand="Mine")
        none = self.product("None", "A seed with no brand mentioned. Brand new variety.")
        self.run_migration()
        keep.refresh_from_db()
        none.refresh_from_db()
        self.assertEqual((keep.brand, keep.description), ("Mine", "Brand: Other\n\nText"))
        self.assertEqual((none.brand, none.description), ("", "A seed with no brand mentioned. Brand new variety."))

    def test_the_brand_is_then_bold_on_the_cards(self):
        self.product("Mahindi", "Brand: STAHA\n\nPack size: 1 kg")
        self.run_migration()
        self.assertContains(self.client.get(reverse("website:marketplace")), "<strong>STAHA</strong>")
        self.assertNotContains(self.client.get(reverse("website:marketplace")), "Brand: STAHA")

    def test_farmer_talk_is_not_in_the_navigation_but_its_pages_still_exist(self):
        page = self.client.get(reverse("website:home"))
        self.assertNotContains(page, "Farmer Talk")
        self.assertNotContains(page, f'href="{reverse("community:discussion_list")}"')
        self.assertEqual(self.client.get(reverse("community:discussion_list")).status_code, 200)

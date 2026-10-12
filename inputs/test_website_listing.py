from datetime import timedelta
from decimal import Decimal

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from website.models import Product

from . import services, website_listing
from .models import RetailAgent, ShopStockItem, WholesaleProduct, WholesaleProductImage
from .tests import InputsTestBase, make_seller, png


class ListingTestBase(InputsTestBase):
    def setUp(self):
        super().setUp()
        self.shop_client = Client()
        self.shop_client.force_login(self.shop_user)
        self.mfr_client = Client()
        self.mfr_client.force_login(self.mfr_user)

    def list_item(self, item=None, client=None, **extra):
        item = item or self.item
        return (client or self.shop_client).post(reverse("inputs:stock_listing", args=[item.pk]), extra, follow=True)

    def list_product(self, product=None, **extra):
        product = product or self.urea
        return self.mfr_client.post(reverse("inputs:product_listing", args=[product.pk]), extra, follow=True)


class ShopListingTests(ListingTestBase):
    def test_one_click_lists_the_stock_item_on_the_website_with_its_details(self):
        self.item.image.save("seed.png", png(), save=True)
        response = self.list_item()
        self.assertContains(response, "is now on the website marketplace")
        self.item.refresh_from_db()
        product = self.item.marketplace_product
        self.assertEqual((product.name, product.price, product.stock, product.supplier), ("Maize seed 2kg", Decimal("10000"), 10, self.shop_user))
        self.assertEqual(product.category.slug, "seeds")
        self.assertTrue(product.is_active)
        self.assertTrue(product.description)
        self.assertEqual(product.images.filter(is_primary=True).count(), 1)  # the photo came along

    def test_it_then_shows_on_the_website(self):
        self.list_item()
        product = self.item.__class__.objects.get(pk=self.item.pk).marketplace_product
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse("website:category_detail", args=[product.category.slug])), "Maize seed 2kg")
        self.assertContains(self.client.get(reverse("website:marketplace")), "Maize seed 2kg")
        self.assertContains(self.client.get(reverse("website:marketplace")), "10,000")

    def test_listing_again_does_not_make_a_second_listing(self):
        self.list_item()
        self.list_item()
        self.assertEqual(Product.objects.filter(supplier=self.shop_user).count(), 1)

    def test_hide_switches_it_off_and_listing_again_switches_the_same_one_back_on(self):
        self.list_item()
        product = ShopStockItem.objects.get(pk=self.item.pk).marketplace_product
        self.assertContains(self.list_item(action="hide"), "hidden from the website")
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 404)
        self.list_item()
        product.refresh_from_db()
        self.assertTrue(product.is_active)
        self.assertEqual(Product.objects.filter(supplier=self.shop_user).count(), 1)

    def test_price_and_stock_changes_follow_to_the_listing(self):
        self.list_item()
        services.record_sale(self.shop, [{"stock_item": self.item.pk, "quantity": 4}], user=self.shop_user, amount_paid=100000)
        product = ShopStockItem.objects.get(pk=self.item.pk).marketplace_product
        self.assertEqual(product.stock, 6)
        item = ShopStockItem.objects.get(pk=self.item.pk)
        item.selling_price = Decimal("12500")
        item.save()
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal("12500"))

    def test_the_sellers_edits_to_the_listing_text_are_kept_when_listing_again(self):
        self.list_item()
        product = ShopStockItem.objects.get(pk=self.item.pk).marketplace_product
        Product.objects.filter(pk=product.pk).update(description="My own words about this seed.")
        self.list_item(action="hide")
        self.list_item()
        product.refresh_from_db()
        self.assertEqual(product.description, "My own words about this seed.")

    def test_an_expired_or_switched_off_item_is_refused_with_a_reason(self):
        self.item.expiry_date = timezone.localdate() - timedelta(days=2)
        self.item.save()
        self.assertContains(self.list_item(), "past its expiry date")
        self.item.expiry_date = None
        self.item.is_active = False
        self.item.save()
        self.assertContains(self.list_item(), "switched off in your stock")
        self.assertFalse(Product.objects.exists())

    def test_the_details_of_a_linked_catalog_product_are_used(self):
        WholesaleProduct.objects.filter(pk=self.urea.pk).update(description="Nitrogen fertilizer.", composition="46% N", target_crops=["Maize", "Rice"])
        item = ShopStockItem.objects.create(
            shop=self.shop, wholesale_product=WholesaleProduct.objects.get(pk=self.urea.pk), name="Urea 46% 50kg", brand="Kilimo", category="fertilizer",
            unit="bag", cost_price=Decimal("60000"), selling_price=Decimal("75000"), quantity=Decimal("8"),
        )
        self.list_item(item)
        description = ShopStockItem.objects.get(pk=item.pk).marketplace_product.description
        for text in ("Nitrogen fertilizer.", "Pack size: 50 kg", "Composition: 46% N", "Suitable crops: Maize, Rice"):
            self.assertIn(text, description)
        self.assertNotIn("Brand:", description)  # the brand is its own bold line, not repeated in the text
        self.assertEqual(ShopStockItem.objects.get(pk=item.pk).marketplace_product.brand, "Kilimo")

    def test_a_shop_cannot_list_another_shops_item(self):
        other_user, other_shop = make_seller("0700000099", "agro_input_dealer", "Other Shop")
        theirs = ShopStockItem.objects.create(shop=other_shop, name="Theirs", category="seeds", cost_price=1, selling_price=2, quantity=1)
        self.assertEqual(self.shop_client.post(reverse("inputs:stock_listing", args=[theirs.pk])).status_code, 404)
        self.assertFalse(Product.objects.exists())

    def test_list_all_lists_what_can_be_listed_and_reports_the_rest(self):
        ShopStockItem.objects.create(shop=self.shop, name="Second item", category="pesticides", cost_price=1, selling_price=2, quantity=3)
        ShopStockItem.objects.create(shop=self.shop, name="Old stock", category="seeds", cost_price=1, selling_price=2, quantity=3, expiry_date=timezone.localdate() - timedelta(days=1))
        ShopStockItem.objects.create(shop=self.shop, name="Switched off", category="seeds", cost_price=1, selling_price=2, quantity=3, is_active=False)
        response = self.shop_client.post(reverse("inputs:stock_listing_all"), follow=True)
        self.assertContains(response, "2 products listed")  # the two good ones
        self.assertContains(response, "1 could not be listed")
        self.assertEqual(sorted(Product.objects.values_list("name", flat=True)), ["Maize seed 2kg", "Second item"])
        again = self.shop_client.post(reverse("inputs:stock_listing_all"), follow=True)
        self.assertContains(again, "1 could not be listed")  # still the expired one

    def test_the_stock_page_shows_the_button_and_the_status(self):
        page = self.shop_client.get(reverse("inputs:stock_list"))
        self.assertContains(page, "List on website")
        self.assertContains(page, "Not listed")
        self.assertContains(page, "List all on the website (1)")
        self.list_item()
        page = self.shop_client.get(reverse("inputs:stock_list"))
        self.assertContains(page, "On the website")
        self.assertNotContains(page, "List all on the website")

    def test_the_marketplace_listings_page_points_to_unlisted_stock(self):
        page = self.shop_client.get(reverse("marketplace:supplier_dashboard"))
        self.assertContains(page, "1 product in your Stock is not on the website yet")
        self.assertContains(page, reverse("inputs:stock_list"))
        self.list_item()
        self.assertNotContains(self.shop_client.get(reverse("marketplace:supplier_dashboard")), "not on the website yet")

    def test_the_other_category_is_created_when_needed(self):
        item = ShopStockItem.objects.create(shop=self.shop, name="Odd thing", category="other", cost_price=1, selling_price=2, quantity=1)
        self.list_item(item)
        self.assertEqual(ShopStockItem.objects.get(pk=item.pk).marketplace_product.category.name, "Other Inputs")

    def test_a_shop_without_a_login_account_gets_a_clear_message(self):
        self.shop.user = None
        self.shop.save()
        with self.assertRaises(website_listing.ListingError):
            website_listing.publish_stock_item(ShopStockItem.objects.select_related("shop").get(pk=self.item.pk))

    def test_the_next_link_only_goes_to_this_site(self):
        response = self.shop_client.post(reverse("inputs:stock_listing", args=[self.item.pk]), {"next": "https://evil.example/steal"})
        self.assertEqual(response["Location"], reverse("inputs:stock_list"))


class ManufacturerListingTests(ListingTestBase):
    def test_a_catalog_product_is_listed_at_its_retail_price(self):
        WholesaleProductImage.objects.create(product=self.urea, image=png("urea.png"), is_primary=True)
        WholesaleProduct.objects.filter(pk=self.urea.pk).update(description="High nitrogen top dressing.", composition="46% N")
        self.assertContains(self.list_product(), "is now on the website marketplace")
        product = WholesaleProduct.objects.get(pk=self.urea.pk).marketplace_product
        self.assertEqual((product.name, product.price, product.stock, product.supplier), ("Urea 46%", Decimal("72000"), 100, self.mfr_user))
        self.assertEqual(product.category.slug, "fertilizers")
        self.assertIn("High nitrogen top dressing.", product.description)
        self.assertIn("Composition: 46% N", product.description)
        self.assertEqual(product.images.count(), 1)
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 200)

    def test_without_a_retail_price_the_wholesale_price_is_used(self):
        WholesaleProduct.objects.filter(pk=self.urea.pk).update(suggested_retail_price=None)
        self.list_product()
        self.assertEqual(WholesaleProduct.objects.get(pk=self.urea.pk).marketplace_product.price, Decimal("60000"))

    def test_hide_and_list_again(self):
        self.list_product()
        self.list_product(action="hide")
        self.assertFalse(WholesaleProduct.objects.get(pk=self.urea.pk).marketplace_product.is_active)
        self.list_product()
        self.assertTrue(WholesaleProduct.objects.get(pk=self.urea.pk).marketplace_product.is_active)
        self.assertEqual(Product.objects.count(), 1)

    def test_stock_and_price_follow_the_catalog_product(self):
        self.list_product()
        product = WholesaleProduct.objects.get(pk=self.urea.pk)
        product.stock_available = 40
        product.suggested_retail_price = Decimal("70000")
        product.save()
        listing = Product.objects.get()
        self.assertEqual((listing.stock, listing.price), (40, Decimal("70000")))

    def test_a_hidden_catalog_product_cannot_be_listed(self):
        WholesaleProduct.objects.filter(pk=self.urea.pk).update(is_active=False)
        self.assertContains(self.list_product(), "hidden in your catalog")
        self.assertFalse(Product.objects.exists())

    def test_the_catalog_page_shows_the_button_the_status_and_list_all(self):
        page = self.mfr_client.get(reverse("inputs:manufacturer_products"))
        self.assertContains(page, "Not on the website")
        self.assertContains(page, "List on website")
        self.assertContains(page, "List all on the website (1)")
        self.mfr_client.post(reverse("inputs:products_listing_all"))
        page = self.mfr_client.get(reverse("inputs:manufacturer_products"))
        self.assertContains(page, "On the website")
        self.assertContains(page, "Hide from website")
        self.assertEqual(Product.objects.count(), 1)

    def test_the_marketplace_listings_page_points_to_the_catalog(self):
        page = self.mfr_client.get(reverse("marketplace:supplier_dashboard"))
        self.assertContains(page, "1 product in your Catalog is not on the website yet")
        self.assertContains(page, reverse("inputs:manufacturer_products"))

    def test_shops_cannot_use_the_manufacturer_buttons_and_vice_versa(self):
        self.assertEqual(self.shop_client.post(reverse("inputs:product_listing", args=[self.urea.pk])).status_code, 302)
        self.assertEqual(self.mfr_client.post(reverse("inputs:stock_listing", args=[self.item.pk])).status_code, 302)
        self.assertFalse(Product.objects.exists())

    def test_one_manufacturer_cannot_list_anothers_product(self):
        other_user, other = make_seller("0700000098", "manufacturer", "Other Maker")
        theirs = WholesaleProduct.objects.create(manufacturer=other, name="Theirs", category="seeds", wholesale_price=Decimal("100"))
        self.assertEqual(self.mfr_client.post(reverse("inputs:product_listing", args=[theirs.pk])).status_code, 404)


class BrandOnTheListingTests(ListingTestBase):
    def test_the_brand_is_copied_from_the_stock_item_or_its_catalog_product(self):
        ShopStockItem.objects.filter(pk=self.item.pk).update(brand="Zamseed")
        self.list_item()
        self.assertEqual(Product.objects.get().brand, "Zamseed")
        WholesaleProduct.objects.filter(pk=self.urea.pk).update(brand="Yara")
        self.list_product()
        self.assertEqual(Product.objects.get(name="Urea 46%").brand, "Yara")
        linked = ShopStockItem.objects.create(
            shop=self.shop, wholesale_product=WholesaleProduct.objects.get(pk=self.urea.pk), name="Urea shop pack", category="fertilizer",
            cost_price=1, selling_price=2, quantity=3,
        )
        self.list_item(linked)
        self.assertEqual(ShopStockItem.objects.get(pk=linked.pk).marketplace_product.brand, "Yara")  # falls back to the catalog brand

    def test_the_brand_is_bold_on_every_page_a_listing_appears(self):
        ShopStockItem.objects.filter(pk=self.item.pk).update(brand="Zamseed")
        self.list_item()
        product = Product.objects.get()
        self.assertContains(self.client.get(product.get_absolute_url()), "<strong>Zamseed</strong>")
        self.assertContains(self.client.get(reverse("website:category_detail", args=[product.category.slug])), "<strong>Zamseed</strong>")
        self.assertContains(self.client.get(reverse("website:marketplace")), "<strong>Zamseed</strong>")

    def test_nothing_is_shown_when_there_is_no_brand(self):
        self.list_item()
        self.assertNotContains(self.client.get(reverse("website:marketplace")), "<strong></strong>")
        self.assertNotContains(self.client.get(Product.objects.get().get_absolute_url()), "product-brand")

    def test_a_seller_can_set_the_brand_on_a_new_listing(self):
        from website.models import Category

        category = Category.objects.create(name="Brand Test", slug="brand-test")
        response = self.shop_client.post(reverse("marketplace:supplier_product_create"), {
            "category": category.pk, "name": "Hand hoe", "brand": "Tramontina", "description": "Strong hoe.", "price": "9000", "stock": "5", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(name="Hand hoe").brand, "Tramontina")
        self.assertContains(self.client.get(Product.objects.get(name="Hand hoe").get_absolute_url()), "<strong>Tramontina</strong>")

    def test_the_stock_and_catalog_pages_show_the_brand_in_bold(self):
        ShopStockItem.objects.filter(pk=self.item.pk).update(brand="Zamseed")
        WholesaleProduct.objects.filter(pk=self.urea.pk).update(brand="Yara")
        self.assertContains(self.shop_client.get(reverse("inputs:stock_list")), "<strong>Zamseed</strong>")
        self.assertContains(self.mfr_client.get(reverse("inputs:manufacturer_products")), "<strong>Yara</strong>")


class WholesaleOnlyTests(ListingTestBase):
    """A supplier that sells wholesale only: its products stay on the website, sold through its agents, with a minimum order."""

    def go_wholesale_only(self):
        return self.mfr_client.post(reverse("inputs:retail_setting"), follow=True)

    def test_suppliers_sell_to_farmers_by_default_so_nothing_changes_for_existing_ones(self):
        self.assertTrue(self.mfr.sells_to_farmers and self.mfr.retails)
        self.assertContains(self.mfr_client.get(reverse("inputs:manufacturer_products")), "You also sell to farmers directly")

    def test_a_retailing_supplier_lists_for_everyone_with_no_minimum(self):
        self.list_product()
        listing = Product.objects.get()
        self.assertFalse(listing.sold_through_agents)
        self.assertEqual(listing.min_order_quantity, 1)
        self.assertFalse(listing.is_wholesale)

    def test_a_wholesale_only_supplier_lists_its_products_sold_through_agents_with_the_catalog_minimum_order(self):
        self.go_wholesale_only()
        self.assertContains(self.list_product(), "is now on the website marketplace")
        listing = Product.objects.get()
        self.assertTrue(listing.sold_through_agents and listing.is_active)
        self.assertEqual(listing.min_order_quantity, 5)  # the catalog's minimum order for shops
        self.assertTrue(listing.is_wholesale)

    def test_switching_to_wholesale_only_keeps_listings_but_routes_them_through_agents_with_the_minimum(self):
        self.list_product()
        listing = Product.objects.get()
        self.assertEqual((listing.sold_through_agents, listing.min_order_quantity), (False, 1))
        response = self.go_wholesale_only()
        self.assertContains(response, "wholesale only")
        self.assertContains(response, "retail agent for the buyer")
        listing.refresh_from_db()
        self.assertTrue(listing.is_active)  # still on the website
        self.assertEqual((listing.sold_through_agents, listing.min_order_quantity), (True, 5))
        self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 200)

    def test_switching_back_to_retail_removes_the_routing_and_the_minimum(self):
        self.go_wholesale_only()
        self.list_product()
        self.mfr_client.post(reverse("inputs:retail_setting"), {"sells_to_farmers": "on"})
        listing = Product.objects.get()
        self.assertEqual((listing.sold_through_agents, listing.min_order_quantity), (False, 1))

    def test_a_change_to_the_catalog_minimum_reaches_a_wholesale_listing(self):
        self.go_wholesale_only()
        self.list_product()
        product = WholesaleProduct.objects.get(pk=self.urea.pk)
        product.min_order_quantity = 20
        product.save()
        self.assertEqual(Product.objects.get().min_order_quantity, 20)

    def test_the_product_page_says_wholesale_and_shows_the_minimum_order(self):
        self.go_wholesale_only()
        self.list_product()
        page = self.client.get(Product.objects.get().get_absolute_url())
        self.assertContains(page, "Wholesale")
        self.assertContains(page, "Minimum order: 5")
        self.assertContains(page, "Sold through our authorized agents")
        self.assertContains(self.client.get(reverse("website:marketplace")), "min order 5")

    def test_the_catalog_page_explains_where_orders_go(self):
        self.go_wholesale_only()
        page = self.mfr_client.get(reverse("inputs:manufacturer_products"))
        self.assertContains(page, "Wholesale only")
        self.assertContains(page, "goes to your retail agent for the farmer")
        self.assertContains(page, "List on website")  # still available

    def test_the_marketplace_listings_page_points_to_retail_agents(self):
        self.go_wholesale_only()
        page = self.mfr_client.get(reverse("marketplace:supplier_dashboard"))
        self.assertContains(page, "You are set up as wholesale only")
        self.assertContains(page, reverse("inputs:agents"))

    def test_a_manual_listing_by_a_wholesale_only_supplier_is_sold_through_agents(self):
        from website.models import Category

        self.go_wholesale_only()
        category = Category.objects.create(name="Wholesale Test", slug="wholesale-test")
        response = self.mfr_client.post(reverse("marketplace:supplier_product_create"), {
            "category": category.pk, "name": "Bulk maize seed", "brand": "Zamseed", "description": "Seed.", "price": "9000", "stock": "500",
            "min_order_quantity": "50", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        listing = Product.objects.get(name="Bulk maize seed")
        self.assertEqual((listing.sold_through_agents, listing.min_order_quantity), (True, 50))

    def test_agrovets_always_sell_to_farmers(self):
        type(self.shop).objects.filter(pk=self.shop.pk).update(sells_to_farmers=False)
        shop = type(self.shop).objects.get(pk=self.shop.pk)
        self.assertTrue(shop.retails)
        self.assertContains(self.list_item(), "is now on the website marketplace")
        self.assertFalse(Product.objects.get().sold_through_agents)

    def test_a_wholesale_only_seedling_seller_still_has_the_website_buttons(self):
        user, seller = make_seller("0700000077", "seedling_seller", "Green Seedlings")
        seller.sells_to_farmers = False
        seller.save()
        ShopStockItem.objects.create(shop=seller, name="Tomato seedlings", category="seedlings", cost_price=1, selling_price=2, quantity=3)
        client = Client()
        client.force_login(user)
        page = client.get(reverse("inputs:stock_list"))
        self.assertContains(page, "List on website")
        client.post(reverse("inputs:stock_listing_all"))
        self.assertTrue(Product.objects.get().sold_through_agents)

    def test_the_profile_form_and_the_mobile_api_carry_the_setting(self):
        from marketplace.forms import SupplierOnboardingForm

        form = SupplierOnboardingForm(instance=self.mfr)
        self.assertIn("sells_to_farmers", form.fields)
        self.assertEqual(form.fields["sells_to_farmers"].label, "I also sell directly to farmers (retail)")
        from .serializers import SellerSerializer

        self.assertTrue(SellerSerializer(self.mfr).data["sells_to_farmers"])

    def test_only_manufacturers_can_use_the_switch(self):
        self.assertEqual(self.shop_client.post(reverse("inputs:retail_setting")).status_code, 302)
        self.assertTrue(type(self.shop).objects.get(pk=self.shop.pk).sells_to_farmers)


class AgentTestBase(ListingTestBase):
    def setUp(self):
        super().setUp()
        self.agent_user, self.agent = make_seller("0700000066", "agro_input_dealer", "Moshi Agrovet")
        self.agent_client = Client()
        self.agent_client.force_login(self.agent_user)

    def go_wholesale_only(self):
        self.mfr_client.post(reverse("inputs:retail_setting"))

    def stock_of_urea(self, shop=None):
        return ShopStockItem.objects.create(
            shop=shop or self.shop, wholesale_product=WholesaleProduct.objects.get(pk=self.urea.pk), name="Urea 46% 50kg", category="fertilizer",
            cost_price=Decimal("60000"), selling_price=Decimal("75000"), quantity=Decimal("8"),
        )

    def appoint(self, shop=None, region="Kilimanjaro"):
        return self.mfr_client.post(reverse("inputs:agent_add", args=[(shop or self.agent).pk]), {"region": region}, follow=True)



class RetailAgentTests(AgentTestBase):
    def test_a_supplier_finds_a_registered_agrovet_and_appoints_it(self):
        page = self.mfr_client.get(reverse("inputs:agents"), {"q": "Moshi"})
        self.assertContains(page, "Moshi Agrovet")
        self.assertContains(page, "Appoint for this region")
        self.assertContains(self.appoint(), "is now your retail agent in Kilimanjaro")
        self.assertEqual(self.mfr.retail_agents.count(), 1)
        self.assertContains(self.mfr_client.get(reverse("inputs:agents")), "Moshi Agrovet")

    def test_appointing_twice_does_not_duplicate(self):
        self.appoint()
        self.assertContains(self.appoint(), "already your retail agent in Kilimanjaro")
        self.assertEqual(self.mfr.retail_agents.count(), 1)

    def test_only_registered_agrovets_can_be_appointed_and_only_by_suppliers(self):
        other_user, other_maker = make_seller("0700000055", "manufacturer", "Other Maker")
        self.assertEqual(self.mfr_client.post(reverse("inputs:agent_add", args=[other_maker.pk])).status_code, 404)
        self.assertEqual(self.agent_client.post(reverse("inputs:agent_add", args=[self.shop.pk])).status_code, 302)
        self.assertFalse(self.mfr.retail_agents.exists())
        self.assertNotContains(self.mfr_client.get(reverse("inputs:agents"), {"q": "Other Maker"}), "Appoint for this region")

    def test_when_the_supplier_is_wholesale_only_only_its_agents_can_list_its_products_on_the_website(self):
        self.go_wholesale_only()
        stranger_item = self.stock_of_urea(self.shop)
        refused = self.list_item(stranger_item)
        self.assertContains(refused, "sells wholesale only. Ask them to appoint you as a retail agent")
        self.assertFalse(Product.objects.filter(is_active=True).exists())

        agent_item = self.stock_of_urea(self.agent)
        self.appoint()
        accepted = self.list_item(agent_item, client=self.agent_client)
        self.assertContains(accepted, "is now on the website marketplace")
        description = ShopStockItem.objects.get(pk=agent_item.pk).marketplace_product.description
        self.assertIn("authorized retail agent of Kilimo Fertilizers Ltd in Kilimanjaro", description)

    def test_a_supplier_that_retails_needs_no_agents_for_shops_to_list_its_products(self):
        item = self.stock_of_urea(self.shop)
        self.assertContains(self.list_item(item), "is now on the website marketplace")

    def test_removing_an_agent_takes_its_listings_of_that_supplier_off_the_website(self):
        self.go_wholesale_only()
        self.appoint()
        item = self.stock_of_urea(self.agent)
        self.list_item(item, client=self.agent_client)
        listing = ShopStockItem.objects.get(pk=item.pk).marketplace_product
        self.assertTrue(listing.is_active)
        link = self.mfr.retail_agents.get()
        response = self.mfr_client.post(reverse("inputs:agent_remove", args=[link.pk]), follow=True)
        self.assertContains(response, "no longer your retail agent")
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)
        self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 404)
        self.assertFalse(self.mfr.retail_agents.exists())

    def test_removing_an_agent_does_not_hide_anything_when_the_supplier_retails(self):
        self.appoint()
        item = self.stock_of_urea(self.agent)
        self.list_item(item, client=self.agent_client)
        self.mfr_client.post(reverse("inputs:agent_remove", args=[self.mfr.retail_agents.get().pk]))
        self.assertTrue(ShopStockItem.objects.get(pk=item.pk).marketplace_product.is_active)

    def test_one_supplier_cannot_remove_anothers_agent(self):
        other_user, other_maker = make_seller("0700000054", "manufacturer", "Other Maker")
        link = RetailAgent.objects.create(supplier=other_maker, agent=self.agent, region="Arusha")
        self.assertEqual(self.mfr_client.post(reverse("inputs:agent_remove", args=[link.pk])).status_code, 404)

    def test_the_agents_page_counts_stock_and_website_listings(self):
        self.appoint()
        item = self.stock_of_urea(self.agent)
        self.stock_of_urea(self.agent)
        self.list_item(item, client=self.agent_client)
        page = self.mfr_client.get(reverse("inputs:agents"))
        self.assertContains(page, "2 of your products in their stock, 1 on the website")
        self.assertContains(page, "Kilimanjaro")

    def test_an_agent_sees_whose_agent_they_are_in_the_catalog(self):
        self.assertNotContains(self.agent_client.get(reverse("inputs:catalog"), {"region": ""}), "You are their retail agent")
        self.appoint()
        self.appoint(region="Arusha")
        self.assertContains(self.agent_client.get(reverse("inputs:catalog"), {"region": ""}), "You are their retail agent in Arusha, Kilimanjaro")

    def test_the_agents_tab_is_for_suppliers(self):
        self.assertContains(self.mfr_client.get(reverse("inputs:manufacturer_dashboard")), reverse("inputs:agents"))
        self.assertNotContains(self.agent_client.get(reverse("inputs:shop_dashboard")), reverse("inputs:agents"))


class AgentRegionTests(AgentTestBase):
    """Agents are appointed region by region."""

    def test_an_appointment_needs_a_valid_region(self):
        for region in ("", "Atlantis"):
            response = self.mfr_client.post(reverse("inputs:agent_add", args=[self.agent.pk]), {"region": region}, follow=True)
            self.assertContains(response, "Choose the region this agent will sell in")
        self.assertFalse(self.mfr.retail_agents.exists())

    def test_the_search_preselects_the_shops_own_region(self):
        type(self.agent).objects.filter(pk=self.agent.pk).update(region="Kilimanjaro")
        page = self.mfr_client.get(reverse("inputs:agents"), {"q": "Moshi"})
        self.assertContains(page, '<option value="Kilimanjaro" selected>Kilimanjaro</option>')

    def test_the_same_agrovet_can_cover_several_regions_and_each_is_listed_under_its_region(self):
        self.appoint(region="Kilimanjaro")
        self.appoint(region="Manyara")
        self.assertEqual(self.mfr.retail_agents.count(), 2)
        page = self.mfr_client.get(reverse("inputs:agents"))
        self.assertContains(page, "2 regions")
        self.assertContains(page, "1 agent<")  # one agrovet, two regions
        self.assertContains(page, "Regions without an agent (29)")
        self.assertNotContains(page, "Manyara, ")  # a covered region is not in the open list

    def test_several_agrovets_can_share_a_region(self):
        other_user, other_agent = make_seller("0700000044", "agro_input_dealer", "Hai Agrovet")
        self.appoint(region="Kilimanjaro")
        self.appoint(other_agent, region="Kilimanjaro")
        page = self.mfr_client.get(reverse("inputs:agents"))
        self.assertContains(page, "Moshi Agrovet")
        self.assertContains(page, "Hai Agrovet")
        self.assertContains(page, "1 region")

    def test_the_listing_names_every_region_the_agent_covers(self):
        self.go_wholesale_only()
        self.appoint(region="Kilimanjaro")
        self.appoint(region="Arusha")
        item = self.stock_of_urea(self.agent)
        self.list_item(item, client=self.agent_client)
        description = ShopStockItem.objects.get(pk=item.pk).marketplace_product.description
        self.assertIn("authorized retail agent of Kilimo Fertilizers Ltd in Arusha, Kilimanjaro", description)

    def test_removing_one_region_keeps_the_listings_while_another_region_remains(self):
        self.go_wholesale_only()
        self.appoint(region="Kilimanjaro")
        self.appoint(region="Arusha")
        item = self.stock_of_urea(self.agent)
        self.list_item(item, client=self.agent_client)
        listing = ShopStockItem.objects.get(pk=item.pk).marketplace_product
        first = self.mfr.retail_agents.get(region="Arusha")
        self.assertContains(self.mfr_client.post(reverse("inputs:agent_remove", args=[first.pk]), follow=True), "no longer your retail agent in Arusha")
        listing.refresh_from_db()
        self.assertTrue(listing.is_active)
        last = self.mfr.retail_agents.get()
        self.assertContains(self.mfr_client.post(reverse("inputs:agent_remove", args=[last.pk]), follow=True), "website listings of your products were hidden")
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)

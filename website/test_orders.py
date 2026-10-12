from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse

from inputs import website_listing
from inputs.models import RetailAgent, ShopStockItem, WholesaleProduct
from inputs.tests import InputsTestBase, make_seller

from website.models import Cart, CartItem, Order, OrderLine, Product

User = get_user_model()


class OrderTestBase(InputsTestBase):
    """A wholesale-only supplier (Kilimo Fertilizers) with urea on the website, and agrovets that can be its agents."""

    def setUp(self):
        super().setUp()
        self.mfr.sells_to_farmers = False
        self.mfr.save()
        self.mfr_user.email = "supplier@kilimo.test"
        self.mfr_user.save()
        website_listing.publish_wholesale(WholesaleProduct.objects.get(pk=self.urea.pk))
        self.listing = Product.objects.get()
        self.buyer = User.objects.create_user(phone_number="0711555000", password="pass12345", email="farmer@x.test", first_name="Niko", last_name="Simiyu")
        self.client = Client()
        self.client.force_login(self.buyer)

        self.moshi_user, self.moshi = make_seller("0700000061", "agro_input_dealer", "Moshi Agrovet")
        self.hai_user, self.hai = make_seller("0700000062", "agro_input_dealer", "Hai Agrovet")
        self.arusha_user, self.arusha = make_seller("0700000063", "agro_input_dealer", "Arusha Agrovet")
        for user, email in ((self.moshi_user, "moshi@x.test"), (self.hai_user, "hai@x.test"), (self.arusha_user, "arusha@x.test")):
            user.email = email
            user.save()

    def appoint(self, agent, region):
        return RetailAgent.objects.create(supplier=self.mfr, agent=agent, region=region)

    def stock(self, agent, quantity):
        return ShopStockItem.objects.create(
            shop=agent, wholesale_product=WholesaleProduct.objects.get(pk=self.urea.pk), name="Urea 46% 50kg", category="fertilizer",
            cost_price=Decimal("60000"), selling_price=Decimal("75000"), quantity=Decimal(quantity),
        )

    def fill_cart(self, quantity=5, product=None):
        cart, _ = Cart.objects.get_or_create(user=self.buyer)
        CartItem.objects.create(cart=cart, product=product or self.listing, quantity=quantity)
        return cart

    def checkout(self, **fields):
        data = {"first_name": "Niko", "last_name": "Simiyu", "email": "farmer@x.test", "phone_number": "0711555000",
                "address": "Near the market", "city": "Moshi", "region": "Kilimanjaro", "delivery_option": ""}
        data.update(fields)
        return self.client.post(reverse("website:checkout"), data, follow=True)

    def the_order(self):
        return Order.objects.get()

    def the_line(self):
        return OrderLine.objects.get()


class CheckoutTests(OrderTestBase):
    def test_an_order_records_what_was_bought_and_where_it_goes(self):
        self.fill_cart(5)
        response = self.checkout()
        self.assertEqual(response.status_code, 200)
        order = self.the_order()
        self.assertEqual((order.buyer_name, order.phone_number, order.delivery_region), ("Niko Simiyu", "0711555000", "Kilimanjaro"))
        self.assertIn("Near the market", order.shipping_address)
        self.assertIn("Kilimanjaro", order.shipping_address)
        line = self.the_line()
        self.assertEqual((line.product, line.quantity, line.unit_price, line.region), (self.listing, 5, Decimal("72000"), "Kilimanjaro"))
        self.assertEqual(line.product_name, "Urea 46%")
        self.assertFalse(CartItem.objects.exists())  # the cart was emptied

    def test_the_order_pages_exist_and_show_the_items(self):
        self.fill_cart(5)
        self.checkout()
        order = self.the_order()
        detail = self.client.get(reverse("website:order_detail", args=[order.pk]))
        self.assertContains(detail, "Urea 46%")
        self.assertContains(detail, "Order #%d" % order.pk)
        listing = self.client.get(reverse("website:order_list"))
        self.assertContains(listing, "Order #%d" % order.pk)
        self.assertContains(listing, "deliver to Kilimanjaro")

    def test_the_buyers_orders_are_private(self):
        self.fill_cart(5)
        self.checkout()
        other = Client()
        other.force_login(User.objects.create_user(phone_number="0711000009", password="pass12345"))
        self.assertEqual(other.get(reverse("website:order_detail", args=[self.the_order().pk])).status_code, 404)

    def test_a_region_is_required_and_must_be_a_real_one(self):
        self.fill_cart(5)
        for region in ("", "Atlantis"):
            response = self.checkout(region=region)
            self.assertContains(response, "Choose the region to deliver to")
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CartItem.objects.exists())

    def test_a_phone_number_and_address_are_required(self):
        self.fill_cart(5)
        self.assertContains(self.checkout(phone_number=""), "phone number")
        self.assertContains(self.checkout(address=""), "street address")
        self.assertFalse(Order.objects.exists())

    def test_an_empty_cart_cannot_be_ordered(self):
        Cart.objects.create(user=self.buyer)
        self.assertContains(self.checkout(), "Your cart is empty")
        self.assertFalse(Order.objects.exists())

    def test_the_checkout_offers_tanzanian_regions_not_kenyan_counties(self):
        self.fill_cart(5)
        page = self.client.get(reverse("website:checkout"))
        self.assertContains(page, '<option value="Kilimanjaro"')
        self.assertContains(page, "Region to deliver to")
        for kenyan in ("Nairobi", "Mombasa", "KSh", "Postal Code"):
            self.assertNotContains(page, kenyan)


class RoutingTests(OrderTestBase):
    def test_the_order_goes_to_the_agent_for_the_buyers_region(self):
        self.appoint(self.moshi, "Kilimanjaro")
        self.appoint(self.arusha, "Arusha")
        self.fill_cart(5)
        self.checkout(region="Kilimanjaro")
        line = self.the_line()
        self.assertEqual((line.route, line.fulfilled_by, line.seller), ("agent", self.moshi_user, self.mfr_user))
        self.assertEqual(line.deliverer_name, "Moshi Agrovet")

    def test_another_region_goes_to_that_regions_agent(self):
        self.appoint(self.moshi, "Kilimanjaro")
        self.appoint(self.arusha, "Arusha")
        self.fill_cart(5)
        self.checkout(region="Arusha")
        self.assertEqual(self.the_line().fulfilled_by, self.arusha_user)

    def test_with_two_agents_in_a_region_the_one_with_the_product_in_stock_gets_it(self):
        self.appoint(self.moshi, "Kilimanjaro")
        self.appoint(self.hai, "Kilimanjaro")
        self.stock(self.hai, 20)
        self.stock(self.moshi, 2)  # not enough for 5
        self.fill_cart(5)
        self.checkout()
        self.assertEqual(self.the_line().fulfilled_by, self.hai_user)

    def test_with_equal_stock_the_agent_with_the_fewest_open_orders_gets_it(self):
        self.appoint(self.moshi, "Kilimanjaro")
        self.appoint(self.hai, "Kilimanjaro")
        self.stock(self.moshi, 50)
        self.stock(self.hai, 50)
        self.fill_cart(5)
        self.checkout()
        first = self.the_line().fulfilled_by
        self.fill_cart(5)
        self.checkout()
        second = OrderLine.objects.order_by("-pk").first().fulfilled_by
        self.assertNotEqual(first, second)  # the second order goes to the agent who has less waiting

    def test_with_no_agent_in_the_region_the_supplier_gets_it_and_is_told(self):
        self.appoint(self.arusha, "Arusha")
        self.fill_cart(5)
        self.checkout(region="Kilimanjaro")
        line = self.the_line()
        self.assertEqual((line.route, line.fulfilled_by), ("no_agent", self.mfr_user))
        subjects = [m.subject for m in mail.outbox]
        self.assertIn(f"Demand in Kilimanjaro with no agent: order #{self.the_order().pk}", subjects)
        message = next(m for m in mail.outbox if m.to == ["supplier@kilimo.test"])
        self.assertIn("no retail agent there yet", message.body)
        self.assertIn("ask Mkulima Smart to deliver it", message.body)
        self.assertIn("Niko Simiyu", message.body)

    def test_the_buyer_is_told_when_no_agent_covers_the_region(self):
        self.fill_cart(5)
        self.checkout()
        page = self.client.get(reverse("website:order_detail", args=[self.the_order().pk]))
        self.assertContains(page, "No agent in Kilimanjaro yet")
        self.assertContains(page, "The supplier has been told about your order")

    def test_the_agent_is_emailed_with_the_buyer_and_the_items(self):
        self.appoint(self.moshi, "Kilimanjaro")
        self.fill_cart(5)
        self.checkout()
        message = next(m for m in mail.outbox if m.to == ["moshi@x.test"])
        self.assertIn("New website order", message.subject)
        self.assertIn("5 x Urea 46%", message.body)
        self.assertIn("0711555000", message.body)
        self.assertNotIn("supplier@kilimo.test", [r for m in mail.outbox for r in m.to if "Demand" in m.subject])

    def test_a_product_the_seller_delivers_itself_ignores_the_region(self):
        self.mfr.sells_to_farmers = True
        self.mfr.save()
        self.appoint(self.moshi, "Kilimanjaro")
        self.fill_cart(1)
        self.checkout(region="Arusha")
        line = self.the_line()
        self.assertEqual((line.route, line.fulfilled_by), ("seller", self.mfr_user))

    def test_an_agent_without_a_login_account_is_skipped(self):
        self.moshi.user = None
        self.moshi.save()
        self.appoint(self.moshi, "Kilimanjaro")
        self.fill_cart(5)
        self.checkout()
        self.assertEqual(self.the_line().route, "no_agent")

    def test_a_cart_with_several_products_is_split_by_who_delivers(self):
        self.appoint(self.moshi, "Kilimanjaro")
        shop_item = ShopStockItem.objects.create(shop=self.shop, name="Maize seed 2kg", category="seeds", cost_price=1, selling_price=10000, quantity=9)
        website_listing.publish_stock_item(shop_item)
        shop_listing = Product.objects.get(name="Maize seed 2kg")
        self.fill_cart(5)
        self.fill_cart(1, product=shop_listing)
        self.checkout()
        by_product = {line.product_name: line for line in OrderLine.objects.all()}
        self.assertEqual(by_product["Urea 46%"].fulfilled_by, self.moshi_user)
        self.assertEqual(by_product["Maize seed 2kg"].fulfilled_by, self.shop_user)
        self.assertEqual(Order.objects.count(), 1)


class MinimumOrderTests(OrderTestBase):
    def test_adding_a_wholesale_product_starts_at_the_minimum(self):
        response = self.client.get(reverse("website:add_to_cart", args=[self.listing.pk]), follow=True)
        item = CartItem.objects.get()
        self.assertEqual(item.quantity, 5)
        self.assertContains(response, "minimum order of 5")

    def test_adding_it_again_adds_one_more(self):
        self.client.get(reverse("website:add_to_cart", args=[self.listing.pk]))
        self.client.get(reverse("website:add_to_cart", args=[self.listing.pk]))
        self.assertEqual(CartItem.objects.get().quantity, 6)

    def test_the_cart_will_not_go_below_the_minimum(self):
        self.fill_cart(8)
        item = CartItem.objects.get()
        response = self.client.post(reverse("website:update_cart_item", args=[item.pk]), {"quantity": "2"}, follow=True)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)
        self.assertContains(response, "minimum order of 5")

    def test_removing_the_item_with_zero_still_works(self):
        self.fill_cart(8)
        item = CartItem.objects.get()
        self.client.post(reverse("website:update_cart_item", args=[item.pk]), {"quantity": "0"})
        self.assertFalse(CartItem.objects.exists())

    def test_the_cart_page_sets_the_minimum_on_the_quantity_box(self):
        self.fill_cart(8)
        self.assertContains(self.client.get(reverse("website:cart")), 'min="5"')

    def test_checkout_refuses_a_quantity_below_the_minimum(self):
        self.fill_cart(2)  # as if set before the minimum was raised
        response = self.checkout()
        self.assertContains(response, "minimum order of 5")
        self.assertFalse(Order.objects.exists())

    def test_it_cannot_be_added_when_stock_is_below_the_minimum(self):
        Product.objects.filter(pk=self.listing.pk).update(stock=3)
        response = self.client.get(reverse("website:add_to_cart", args=[self.listing.pk]), follow=True)
        self.assertFalse(CartItem.objects.exists())
        self.assertContains(response, "only 3 are in stock")

    def test_a_normal_product_has_no_minimum(self):
        retail = Product.objects.create(
            name="Hoe", slug="hoe", category=self.listing.category, description="d", price=9000, stock=10, supplier=self.shop_user,
        )
        self.client.get(reverse("website:add_to_cart", args=[retail.pk]))
        self.assertEqual(CartItem.objects.get().quantity, 1)


class OptionalFeesTests(OrderTestBase):
    """Delivery and VAT are added only when the buyer ticks them."""

    def test_by_default_the_total_is_just_the_products(self):
        self.fill_cart(5)
        self.checkout()
        order = self.the_order()
        self.assertEqual(order.total_amount, Decimal("360000"))  # 5 x 72,000, nothing added
        self.assertEqual((order.delivery_option, order.delivery_fee, order.vat_amount), ("", 0, 0))

    def test_standard_and_express_delivery_add_their_fee_only_when_chosen(self):
        self.fill_cart(5)
        self.checkout(delivery_option="standard")
        order = self.the_order()
        self.assertEqual((order.delivery_option, order.delivery_fee, order.total_amount), ("standard", Decimal("350"), Decimal("360350")))
        Order.objects.all().delete()
        self.fill_cart(5)
        self.checkout(delivery_option="express")
        self.assertEqual(self.the_order().total_amount, Decimal("360650"))

    def test_vat_is_added_only_when_ticked_at_eighteen_percent(self):
        self.fill_cart(5)
        self.checkout(add_vat="on")
        order = self.the_order()
        self.assertEqual((order.vat_amount, order.total_amount), (Decimal("64800"), Decimal("424800")))

    def test_delivery_and_vat_together(self):
        self.fill_cart(5)
        self.checkout(delivery_option="express", add_vat="on")
        self.assertEqual(self.the_order().total_amount, Decimal("360000") + Decimal("650") + Decimal("64800"))

    def test_an_unknown_delivery_option_adds_nothing(self):
        self.fill_cart(5)
        self.checkout(delivery_option="drone")
        order = self.the_order()
        self.assertEqual((order.delivery_option, order.delivery_fee, order.total_amount), ("", 0, Decimal("360000")))

    def test_the_cart_page_adds_nothing_and_says_so(self):
        self.fill_cart(5)
        page = self.client.get(reverse("website:cart"))
        self.assertNotContains(page, "Delivery Fee")
        self.assertNotContains(page, "Tax (")
        self.assertContains(page, "not added automatically")
        self.assertEqual(page.context["cart_total_with_fees"], Decimal("360000"))

    def test_the_checkout_starts_with_no_delivery_and_vat_unticked(self):
        self.fill_cart(5)
        page = self.client.get(reverse("website:checkout"))
        self.assertEqual(page.context["cart_total_with_fees"], Decimal("360000"))
        self.assertContains(page, 'id="noDelivery" value="" checked')
        self.assertNotContains(page, 'id="addVat" checked')
        self.assertContains(page, "Add VAT (18%)")
        self.assertContains(page, "+ TSh 350")
        self.assertContains(page, "Not added")

    def test_the_choices_survive_a_form_error(self):
        self.fill_cart(5)
        response = self.checkout(region="", delivery_option="express", add_vat="on")
        self.assertContains(response, "Choose the region to deliver to")
        self.assertContains(response, 'value="express" checked')
        self.assertContains(response, 'id="addVat" checked')


class SellerInboxTests(OrderTestBase):
    def setUp(self):
        super().setUp()
        self.appoint(self.moshi, "Kilimanjaro")
        self.moshi_client = Client()
        self.moshi_client.force_login(self.moshi_user)
        self.fill_cart(5)
        self.checkout()
        self.line = self.the_line()

    def test_the_agent_sees_the_order_with_the_buyers_details(self):
        page = self.moshi_client.get(reverse("inputs:web_orders"))
        self.assertContains(page, "Urea 46%")
        self.assertContains(page, "Niko Simiyu")
        self.assertContains(page, "0711555000")
        self.assertContains(page, "Passed to you as the agent for Kilimanjaro")

    def test_the_nav_shows_a_count_of_new_orders(self):
        page = self.moshi_client.get(reverse("inputs:shop_dashboard"))
        self.assertContains(page, "Website Orders")
        self.assertContains(page, '<span class="in-badge">1</span>')

    def test_confirming_and_delivering_moves_the_order_along(self):
        self.moshi_client.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "confirm"})
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, "confirmed")
        self.assertEqual(Order.objects.get().status, "processing")
        self.moshi_client.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "deliver"})
        self.assertEqual(Order.objects.get().status, "delivered")
        page = self.client.get(reverse("website:order_detail", args=[Order.objects.get().pk]))
        self.assertContains(page, "Delivered")

    def test_cancelling_all_items_cancels_the_order(self):
        self.moshi_client.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "cancel"})
        self.assertEqual(Order.objects.get().status, "cancelled")

    def test_only_the_person_who_has_to_deliver_can_change_it(self):
        other = Client()
        other.force_login(self.hai_user)
        self.assertEqual(other.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "deliver"}).status_code, 404)
        self.client.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "deliver"})
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, "new")

    def test_finished_orders_leave_the_to_deliver_list_but_stay_in_all(self):
        self.moshi_client.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "deliver"})
        self.moshi_client.get(reverse("inputs:web_orders"))  # shows the one-time "delivered" message
        self.assertNotContains(self.moshi_client.get(reverse("inputs:web_orders")), "Urea 46%")
        self.assertContains(self.moshi_client.get(reverse("inputs:web_orders"), {"show": "all"}), "Urea 46%")

    def test_the_supplier_can_ask_mkulima_smart_to_deliver_when_it_has_no_agent(self):
        OrderLine.objects.all().delete()
        Order.objects.all().delete()
        RetailAgent.objects.all().delete()
        self.fill_cart(5)
        self.checkout()
        line = self.the_line()
        supplier = Client()
        supplier.force_login(self.mfr_user)
        page = supplier.get(reverse("inputs:web_orders"))
        self.assertContains(page, "Demand in Kilimanjaro, where you have no agent")
        self.assertContains(page, "Ask Mkulima Smart to deliver")
        supplier.post(reverse("inputs:web_order_update", args=[line.pk]), {"action": "via_platform"})
        line.refresh_from_db()
        self.assertTrue(line.via_platform)
        self.assertEqual(line.status, "confirmed")
        self.assertContains(self.client.get(reverse("website:order_detail", args=[line.order_id])), "arranging delivery to you")

    def test_via_platform_is_only_for_orders_with_no_agent(self):
        self.moshi_client.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "via_platform"})
        self.line.refresh_from_db()
        self.assertFalse(self.line.via_platform)


class OpsWebOrdersTests(OrderTestBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(password="pass12345", email="admin@mkulima.test")
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)
        self.fill_cart(5)
        self.checkout()  # no agent: demand
        self.line = self.the_line()

    def test_demand_without_an_agent_is_flagged_on_the_overview_and_listed(self):
        self.assertContains(self.admin_client.get(reverse("ops:overview")), "in regions where the supplier has no agent")
        page = self.admin_client.get(reverse("ops:web_orders"), {"show": "no_agent"})
        self.assertContains(page, "Urea 46%")
        self.assertContains(page, "No agent in Kilimanjaro")
        self.assertContains(page, "Niko Simiyu")

    def test_deliveries_suppliers_asked_us_to_make_are_flagged_and_can_be_marked_delivered(self):
        supplier = Client()
        supplier.force_login(self.mfr_user)
        supplier.post(reverse("inputs:web_order_update", args=[self.line.pk]), {"action": "via_platform"})
        overview = self.admin_client.get(reverse("ops:overview"))
        self.assertContains(overview, "suppliers asked Mkulima Smart to deliver")
        self.assertContains(self.admin_client.get(reverse("ops:web_orders")), "Asked us to deliver")
        self.admin_client.post(reverse("ops:web_order_update", args=[self.line.pk]), {"action": "deliver"})
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, "delivered")
        self.assertEqual(Order.objects.get().status, "delivered")
        self.assertNotContains(self.admin_client.get(reverse("ops:overview")), "suppliers asked Mkulima Smart to deliver")

    def test_only_administrators(self):
        staff = Client()
        staff.force_login(User.objects.create_user(password="pass12345", email="staff@gov.test", is_staff=True))
        self.assertEqual(staff.get(reverse("ops:web_orders")).status_code, 403)
        self.assertEqual(staff.post(reverse("ops:web_order_update", args=[self.line.pk]), {"action": "deliver"}).status_code, 403)

    def test_it_is_in_the_navigation(self):
        self.assertContains(self.admin_client.get(reverse("ops:overview")), reverse("ops:web_orders"))

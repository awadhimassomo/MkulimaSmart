import hashlib
import hmac
import io
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from inputs import services
from inputs.models import FarmerOrder, Sale, ShopStockItem, StockMovement, WholesaleProduct
from inputs.test_api import jwt_client
from inputs.tests import MEDIA, User, make_seller, png

from .models import PartnerToken, WebhookDelivery, hash_token
from .webhooks import deliver_pending

BASE = "/api/kikapu-bridge"
SECRET = "test-shared-secret"
WEBHOOK_URL = "https://kikapu.test/api/kikapu-bridge/orders/status/"


def ok_response(code=200):
    return mock.Mock(status_code=code, text="ok")


@override_settings(
    MEDIA_ROOT=MEDIA,
    KIKAPU_BRIDGE_REQUIRE_HTTPS=False,
    KIKAPU_BRIDGE_WEBHOOK_URL=WEBHOOK_URL,
    KIKAPU_BRIDGE_WEBHOOK_SECRET=SECRET,
    KIKAPU_BRIDGE_PUBLIC_BASE_URL="https://www.mkulimasmart.co.tz",
)
class BridgeTestBase(TestCase):
    def setUp(self):
        self.shop_user, self.shop = make_seller("0712345678", "agro_input_dealer", "Arusha Agrovet")
        self.shop.region = "Arusha"
        self.shop.district = "Arusha Urban"
        self.shop.latitude = Decimal("-3.386900")
        self.shop.longitude = Decimal("36.683000")
        self.shop.save()
        _, self.mfr = make_seller("0712000000", "manufacturer", "Kilimo Bora Ltd")
        self.npk_product = WholesaleProduct.objects.create(
            manufacturer=self.mfr, name="NPK 17-17-17", category="fertilizer", pack_size="50 kg", unit="bag",
            wholesale_price=60000, composition="17-17-17",
        )
        self.npk = ShopStockItem.objects.create(
            shop=self.shop, wholesale_product=self.npk_product, name="NPK 17-17-17", brand="Yara", category="fertilizer",
            unit="bag", cost_price=60000, selling_price=Decimal("72000"), quantity=Decimal("10"), image=png(),
        )
        self.spray = ShopStockItem.objects.create(
            shop=self.shop, name="Duduba 1L", category="pesticides", unit="bottle", cost_price=14000,
            selling_price=18000, quantity=Decimal("3"), expiry_date=timezone.localdate() + timedelta(days=100),
        )
        self.token_obj, token = PartnerToken.issue("Kikapu test")
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def order_body(self, **overrides):
        body = {
            "kikapu_order_id": "KP-INP-00482",
            "shop_id": f"shop-{self.shop.pk}",
            "items": [{"input_id": f"input-{self.npk.pk}", "quantity": 2}],
            "farmer": {"name": "Juma Ally", "phone_number": "+255711000001", "delivery_region": "Arusha",
                       "delivery_notes": "Near Kariakoo market"},
        }
        body.update(overrides)
        return body

    def place_order(self, **overrides):
        return self.api.post(f"{BASE}/orders/", self.order_body(**overrides), format="json")


class AuthTests(BridgeTestBase):
    def test_requires_valid_active_token(self):
        self.assertEqual(APIClient().get(f"{BASE}/shops/").status_code, 401)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(bad.get(f"{BASE}/shops/").status_code, 401)
        self.assertEqual(self.api.get(f"{BASE}/shops/").status_code, 200)
        self.token_obj.is_active = False
        self.token_obj.save()
        self.assertEqual(self.api.get(f"{BASE}/shops/").status_code, 401)

    def test_user_jwt_is_not_a_partner_token(self):
        self.assertEqual(jwt_client(self.shop_user).get(f"{BASE}/shops/").status_code, 401)

    def test_only_hash_is_stored_and_command_prints_token_once(self):
        out = io.StringIO()
        call_command("issue_kikapu_token", "--name", "Kikapu prod", stdout=out)
        raw = out.getvalue().strip().splitlines()[-1]
        token = PartnerToken.objects.get(name="Kikapu prod")
        self.assertEqual(token.token_hash, hash_token(raw))
        self.assertNotIn(raw, json.dumps(list(PartnerToken.objects.values()), default=str), "raw token must not be stored")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(client.get(f"{BASE}/shops/").status_code, 200)

    @override_settings(KIKAPU_BRIDGE_REQUIRE_HTTPS=True)
    def test_https_required_in_production(self):
        self.assertEqual(self.api.get(f"{BASE}/shops/").status_code, 403)
        self.assertEqual(self.api.get(f"{BASE}/shops/", secure=True).status_code, 200)


class CatalogTests(BridgeTestBase):
    def test_shops(self):
        _, other = make_seller("0755000000", "agro_input_dealer", "Moshi Inputs")
        other.location = "Moshi, Kilimanjaro"
        other.list_on_kikapu = False
        other.save()
        data = self.api.get(f"{BASE}/shops/").json()
        self.assertEqual(data["count"], 2)  # manufacturers are not shops
        arusha = next(s for s in data["results"] if s["id"] == f"shop-{self.shop.pk}")
        self.assertEqual(arusha, {
            "id": f"shop-{self.shop.pk}", "name": "Arusha Agrovet", "region": "Arusha", "district": "Arusha Urban",
            "latitude": -3.3869, "longitude": 36.683, "phone_number": "+255712345678", "is_active": True,
            "updated_at": arusha["updated_at"],
        })
        moshi = next(s for s in data["results"] if s["id"] == f"shop-{other.pk}")
        self.assertEqual(moshi["region"], "Kilimanjaro")  # guessed from location until they set it
        self.assertFalse(moshi["is_active"])  # opted out of Kikapu

    def test_shops_updated_since(self):
        later = (timezone.now() + timedelta(minutes=5)).isoformat()
        self.assertEqual(self.api.get(f"{BASE}/shops/", {"updated_since": later}).json()["count"], 0)
        self.assertEqual(self.api.get(f"{BASE}/shops/?updated_since=2020-01-01T00:00:00Z").json()["count"], 1)
        self.assertEqual(self.api.get(f"{BASE}/shops/?updated_since=yesterday").status_code, 400)

    def test_inputs_shape_and_mapping(self):
        data = self.api.get(f"{BASE}/inputs/").json()
        npk = next(i for i in data["results"] if i["id"] == f"input-{self.npk.pk}")
        self.assertEqual(npk["shop_id"], f"shop-{self.shop.pk}")
        self.assertEqual(npk["category"], "fertilizer")
        self.assertEqual(npk["unit"], "50 kg bag")
        self.assertEqual(npk["price"], 72000)
        self.assertEqual(npk["stock_quantity"], 10)
        self.assertTrue(npk["in_stock"])
        self.assertTrue(npk["image_url"].startswith("https://www.mkulimasmart.co.tz/media/"))
        self.assertIn("17-17-17", npk["description"])
        spray = next(i for i in data["results"] if i["id"] == f"input-{self.spray.pk}")
        self.assertEqual(spray["category"], "pesticide")

    def test_in_stock_rules(self):
        self.spray.expiry_date = timezone.localdate() - timedelta(days=1)
        self.spray.save()
        self.npk.quantity = Decimal("0.5")
        self.npk.save()
        results = {i["id"]: i for i in self.api.get(f"{BASE}/inputs/").json()["results"]}
        self.assertFalse(results[f"input-{self.spray.pk}"]["in_stock"])  # expired
        self.assertFalse(results[f"input-{self.npk.pk}"]["in_stock"])  # less than one unit

        self.npk.quantity = Decimal("10")
        self.npk.save()
        self.shop.list_on_kikapu = False
        self.shop.save()
        npk = {i["id"]: i for i in self.api.get(f"{BASE}/inputs/").json()["results"]}[f"input-{self.npk.pk}"]
        self.assertFalse(npk["in_stock"])
        self.assertFalse(npk["is_active"])

    def test_input_filters(self):
        self.assertEqual(self.api.get(f"{BASE}/inputs/?category=pesticide").json()["count"], 1)
        self.assertEqual(self.api.get(f"{BASE}/inputs/?category=herbicide").json()["count"], 0)
        self.assertEqual(self.api.get(f"{BASE}/inputs/?shop_id=shop-{self.shop.pk}").json()["count"], 2)
        self.assertEqual(self.api.get(f"{BASE}/inputs/?shop_id=shop-999").json()["count"], 0)

    def test_inputs_updated_since_includes_shop_changes_and_expiry(self):
        since = timezone.now() + timedelta(seconds=1)
        ShopStockItem.objects.filter(pk__in=[self.npk.pk, self.spray.pk]).update(updated_at=since - timedelta(days=3))
        self.assertEqual(self.api.get(f"{BASE}/inputs/", {"updated_since": since.isoformat()}).json()["count"], 0)

        # Expired since the last sync: in_stock flipped even though the row didn't change.
        ShopStockItem.objects.filter(pk=self.spray.pk).update(expiry_date=timezone.localdate() - timedelta(days=1))
        yesterday = (timezone.now() - timedelta(days=2)).isoformat()
        ShopStockItem.objects.filter(pk__in=[self.npk.pk, self.spray.pk]).update(updated_at=timezone.now() - timedelta(days=5))
        type(self.shop).objects.filter(pk=self.shop.pk).update(updated_at=timezone.now() - timedelta(days=5))
        ids = [i["id"] for i in self.api.get(f"{BASE}/inputs/", {"updated_since": yesterday}).json()["results"]]
        self.assertEqual(ids, [f"input-{self.spray.pk}"])

        # Shop paused: all its inputs count as changed.
        self.shop.list_on_kikapu = False
        self.shop.save()
        ids = [i["id"] for i in self.api.get(f"{BASE}/inputs/", {"updated_since": yesterday}).json()["results"]]
        self.assertEqual(sorted(ids), sorted([f"input-{self.npk.pk}", f"input-{self.spray.pk}"]))

    def test_price_poll(self):
        row = self.api.get(f"{BASE}/inputs/prices/?shop_id=shop-{self.shop.pk}").json()["results"][0]
        self.assertEqual(set(row), {"id", "price", "stock_quantity", "in_stock", "updated_at"})


class OrderTests(BridgeTestBase):
    def test_accepts_order_and_reserves_stock(self):
        response = self.place_order()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        order = FarmerOrder.objects.get()
        self.assertEqual(body["mkulima_order_id"], f"MS-{order.pk}")
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["total_price"], 144000)
        self.assertTrue(body["success"])
        self.npk.refresh_from_db()
        self.assertEqual(self.npk.quantity, Decimal("8"))
        self.assertTrue(StockMovement.objects.filter(stock_item=self.npk, reason="farmer_order", change=-2).exists())
        self.assertEqual(order.farmer_phone, "+255711000001")

    def test_rejects_when_sold_out_with_reason(self):
        response = self.place_order(items=[{"input_id": f"input-{self.npk.pk}", "quantity": 11}])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["reason"], "Only 10 bag of NPK 17-17-17 left at Arusha Agrovet.")
        self.assertFalse(FarmerOrder.objects.exists())
        self.npk.refresh_from_db()
        self.assertEqual(self.npk.quantity, Decimal("10"))

        self.shop.list_on_kikapu = False
        self.shop.save()
        self.assertEqual(self.place_order().status_code, 409)

    def test_retry_is_idempotent(self):
        first = self.place_order().json()
        second = self.place_order()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["mkulima_order_id"], first["mkulima_order_id"])
        self.assertEqual(FarmerOrder.objects.count(), 1)
        self.npk.refresh_from_db()
        self.assertEqual(self.npk.quantity, Decimal("8"))  # reserved once

        clash = self.place_order(items=[{"input_id": f"input-{self.npk.pk}", "quantity": 5}])
        self.assertEqual(clash.status_code, 409)
        self.assertEqual(clash.json()["code"], "duplicate_order")

    def test_validation(self):
        response = self.api.post(f"{BASE}/orders/", {"items": [{"input_id": "x", "quantity": 0}]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"kikapu_order_id", "shop_id", "items", "farmer.name", "farmer.phone_number"})

        _, other = make_seller("0755000000", "agro_input_dealer", "Other")
        foreign = ShopStockItem.objects.create(shop=other, name="X", selling_price=1, quantity=5)
        response = self.place_order(items=[{"input_id": f"input-{foreign.pk}", "quantity": 1}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.place_order(shop_id="shop-9999").status_code, 404)

    def test_links_farmer_only_when_phone_matches(self):
        farmer = User.objects.create_user(phone_number="0711000001", password="x" * 10, is_farmer=True)
        stranger = User.objects.create_user(phone_number="0799999999", password="x" * 10)
        self.place_order(farmer={"name": "Juma", "phone_number": "+255711000001", "mkulima_user_id": farmer.pk})
        self.assertEqual(FarmerOrder.objects.get().farmer_user, farmer)
        self.place_order(kikapu_order_id="KP-2", farmer={"name": "Juma", "phone_number": "+255711000001", "mkulima_user_id": stranger.pk})
        self.assertIsNone(FarmerOrder.objects.get(external_order_id="KP-2").farmer_user)

    def test_order_status_lookup(self):
        mid = self.place_order().json()["mkulima_order_id"]
        self.assertEqual(self.api.get(f"{BASE}/orders/{mid}/").json()["status"], "pending")
        self.assertEqual(self.api.get(f"{BASE}/orders/MS-99999/").status_code, 404)


class WebhookTests(BridgeTestBase):
    def setUp(self):
        super().setUp()
        self.place_order()
        self.order = FarmerOrder.objects.get()

    def update(self, status, note=""):
        with self.captureOnCommitCallbacks(execute=True):
            services.update_farmer_order_status(self.order, status, user=self.shop_user, note=note)
        self.order.refresh_from_db()

    @mock.patch("kikapu_bridge.webhooks.requests.post", return_value=ok_response())
    def test_signed_status_update(self, post):
        self.update("confirmed", note="Tunaandaa oda yako")
        post.assert_called_once()
        url = post.call_args.args[0]
        body = post.call_args.kwargs["data"]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(url, WEBHOOK_URL)
        payload = json.loads(body)
        self.assertEqual(payload["kikapu_order_id"], "KP-INP-00482")
        self.assertEqual(payload["mkulima_order_id"], self.order.order_number)
        self.assertEqual(payload["status"], "confirmed")
        self.assertEqual(payload["note"], "Tunaandaa oda yako")
        expected = hmac.new(SECRET.encode(), f"{headers['X-Webhook-Timestamp']}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-Webhook-Signature"], expected)
        self.assertEqual(headers["X-Partner-ID"], "mkulima-smart")
        self.assertNotIn(SECRET, body.decode())
        self.assertIsNotNone(WebhookDelivery.objects.get().delivered_at)

    @override_settings(KIKAPU_BRIDGE_WEBHOOK_SECRET="")
    @mock.patch("kikapu_bridge.webhooks.requests.post")
    def test_nothing_sent_until_configured(self, post):
        self.update("confirmed")
        post.assert_not_called()
        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.attempts, 0)
        self.assertIsNone(delivery.delivered_at)

    @mock.patch("kikapu_bridge.webhooks.requests.post")
    def test_failures_retry_in_order(self, post):
        post.return_value = ok_response(503)
        self.update("confirmed")
        confirmed = WebhookDelivery.objects.get(status="confirmed")
        self.assertEqual(confirmed.attempts, 1)
        self.assertGreater(confirmed.next_attempt_at, timezone.now())

        post.reset_mock()
        post.return_value = ok_response(200)
        self.update("dispatched")
        post.assert_not_called()  # waits behind the failed "confirmed"

        sent, failed = deliver_pending(now=timezone.now() + timedelta(minutes=5))
        self.assertEqual((sent, failed), (2, 0))
        self.assertEqual([json.loads(c.kwargs["data"])["status"] for c in post.call_args_list], ["confirmed", "dispatched"])

    @mock.patch("kikapu_bridge.webhooks.requests.post", return_value=ok_response())
    def test_cancel_returns_stock_and_delivery_records_sale(self, post):
        self.update("cancelled", note="Samahani, gari limeharibika")
        self.npk.refresh_from_db()
        self.assertEqual(self.npk.quantity, Decimal("10"))
        self.assertEqual(json.loads(post.call_args.kwargs["data"])["status"], "cancelled")

        self.place_order(kikapu_order_id="KP-2")
        self.order = FarmerOrder.objects.get(external_order_id="KP-2")
        for status in ("confirmed", "dispatched", "delivered"):
            self.update(status)
        sale = self.order.sale
        self.assertEqual((sale.channel, sale.payment_method, sale.total), ("kikapu", "on_delivery", Decimal("144000")))
        self.npk.refresh_from_db()
        self.assertEqual(self.npk.quantity, Decimal("8"))  # the sale didn't deduct stock a second time
        self.assertEqual(Sale.objects.count(), 1)

    def test_invalid_transition(self):
        with self.assertRaises(services.StockError):
            services.update_farmer_order_status(self.order, "delivered")

    @mock.patch("kikapu_bridge.webhooks.requests.post", return_value=ok_response())
    def test_retry_command(self, post):
        with override_settings(KIKAPU_BRIDGE_WEBHOOK_SECRET=""):
            self.update("confirmed")
        post.assert_not_called()
        out = io.StringIO()
        call_command("send_kikapu_webhooks", stdout=out)
        self.assertIn("Sent 1", out.getvalue())


class ShopHandlesFarmerOrdersTests(BridgeTestBase):
    @mock.patch("kikapu_bridge.webhooks.requests.post", return_value=ok_response())
    def test_web_pages(self, post):
        self.place_order()
        order = FarmerOrder.objects.get()
        self.client.force_login(self.shop_user)
        dashboard = self.client.get("/en/inputs/shop/")
        self.assertContains(dashboard, "Farmer orders to handle")
        self.assertContains(self.client.get("/en/inputs/shop/farmer-orders/"), "Juma Ally")
        page = self.client.get(f"/en/inputs/shop/farmer-orders/{order.pk}/")
        self.assertContains(page, "Confirm order")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/en/inputs/shop/farmer-orders/{order.pk}/", {"status": "confirmed", "note": "Karibu"})
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")
        self.assertContains(self.client.get(f"/en/inputs/shop/farmer-orders/{order.pk}/"), "Farmer notified")

    @mock.patch("kikapu_bridge.webhooks.requests.post", return_value=ok_response())
    def test_mobile_api(self, post):
        self.place_order()
        order = FarmerOrder.objects.get()
        app = jwt_client(self.shop_user)
        listing = app.get("/api/inputs/shop/farmer-orders/").json()
        self.assertEqual(listing["results"][0]["allowed_actions"], ["confirmed", "cancelled"])
        self.assertEqual(app.get("/api/inputs/shop/dashboard/").json()["farmer_orders"]["new_count"], 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = app.post(f"/api/inputs/shop/farmer-orders/{order.pk}/status/", {"status": "confirmed"}, format="json")
        self.assertEqual(response.json()["status"], "confirmed")
        # The webhook is sent on commit; in tests that happens after the response is built.
        detail = app.get(f"/api/inputs/shop/farmer-orders/{order.pk}/").json()
        self.assertEqual(detail["farmer_notified"], {"status": "confirmed", "state": "delivered"})
        bad = app.post(f"/api/inputs/shop/farmer-orders/{order.pk}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_pos_cannot_sell_reserved_stock(self):
        self.place_order(items=[{"input_id": f"input-{self.npk.pk}", "quantity": 10}])
        with self.assertRaises(services.StockError):
            services.record_sale(self.shop, [{"stock_item": self.npk.pk, "quantity": 1}])


class RetryLoopTests(BridgeTestBase):
    @mock.patch("kikapu_bridge.management.commands.send_kikapu_webhooks.time.sleep", side_effect=KeyboardInterrupt)
    @mock.patch("kikapu_bridge.management.commands.send_kikapu_webhooks.deliver_pending", return_value=(1, 0))
    def test_loop_mode_runs_rounds(self, deliver, sleep):
        out = io.StringIO()
        with self.assertRaises(KeyboardInterrupt):
            call_command("send_kikapu_webhooks", "--loop", "--interval", "30", stdout=out)
        deliver.assert_called_once()
        sleep.assert_called_once_with(30)
        self.assertIn("Sent 1, failed 0.", out.getvalue())

    @mock.patch("kikapu_bridge.management.commands.send_kikapu_webhooks.time.sleep", side_effect=[None, KeyboardInterrupt])
    @mock.patch("kikapu_bridge.management.commands.send_kikapu_webhooks.deliver_pending", side_effect=[RuntimeError("db down"), (0, 0)])
    def test_loop_survives_errors(self, deliver, sleep):
        err = io.StringIO()
        with self.assertRaises(KeyboardInterrupt):
            call_command("send_kikapu_webhooks", "--loop", stdout=io.StringIO(), stderr=err)
        self.assertEqual(deliver.call_count, 2)
        self.assertIn("db down", err.getvalue())

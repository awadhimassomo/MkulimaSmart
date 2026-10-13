import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from rest_framework.test import APIClient

from assistant.models import Conversation
from callcenter import services as callcenter
from callcenter.models import Agronomist, Case
from callcenter.tests import make_agronomist
from gova_pp.diagnosis import DiagnosisError
from inputs.models import FarmerOrder, ShopStockItem
from inputs.tests import make_seller
from kikapu_bridge.models import ReplyDelivery
from website.models import Order

from . import outbox, services, text
from .models import Contact, Device, InboundSms, OutboundSms

SENDER = "0712345678"
E164 = "+255712345678"


class GatewayBase(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.device, self.token = Device.issue("office phone 1")
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.url = lambda name, **kw: reverse(f"smsgateway:{name}", kwargs=kw)

    def message(self, body, sender=SENDER, client_id=None, **extra):
        return {"client_id": client_id or str(uuid.uuid4()), "from": sender, "body": body,
                "sent_at": "2026-10-13T09:14:58+03:00", "received_at": "2026-10-13T09:15:02+03:00", "sim_slot": 0, "parts": 1, **extra}

    def upload(self, *items, client=None):
        return (client or self.api).post(self.url("inbox"), {"messages": list(items)}, format="json")

    def text_in(self, body, sender=SENDER):
        """The phone uploads one SMS; returns the stored message."""
        self.upload(self.message(body, sender=sender))
        return InboundSms.objects.latest("id")

    def replies(self, to=E164):
        return list(OutboundSms.objects.filter(to=to).order_by("id").values_list("body", flat=True))


class TextTests(TestCase):
    def test_numbers_in_any_format_become_e164(self):
        for raw in ("0712 345 678", "+255 712 345 678", "255712345678", "712345678", "0255712345678"[1:], "00255712345678"):
            self.assertEqual(text.e164(raw), E164, raw)
        for bad in ("", None, "MPESA", "123", "0712", "+12"):
            self.assertIsNone(text.e164(bad), bad)

    def test_phone_key_and_local_format(self):
        self.assertEqual(text.phone_key("+255 712 345 678"), "712345678")
        self.assertEqual(text.phone_key("0712345678"), "712345678")
        self.assertEqual(text.local_format(E164), "0712 345 678")

    def test_gsm7_ucs2_and_parts(self):
        self.assertEqual(text.analyze("Habari yako"), ("gsm7", 11, 1))
        self.assertEqual(text.analyze("a" * 160)[2], 1)
        self.assertEqual(text.analyze("a" * 161)[2], 2)
        self.assertEqual(text.analyze("a" * 306)[2], 2)
        self.assertEqual(text.analyze("a" * 307)[2], 3)
        self.assertEqual(text.analyze("a{b}")[1], 6)  # the braces cost two each
        self.assertEqual(text.analyze("مرحبا")[0], "ucs2")
        self.assertEqual(text.analyze("م" * 71)[2], 2)

    def test_clean_replaces_curly_quotes_and_tidies_space(self):
        self.assertEqual(text.clean("It’s  “good”\n\n\n\nok – yes"), "It's \"good\"\n\nok - yes")
        self.assertEqual(text.analyze(text.clean("It’s fine"))[0], "gsm7")

    def test_shorten_fits_the_parts_and_ends_cleanly(self):
        long = "neno " * 200
        short = text.shorten(long, max_parts=3)
        self.assertLessEqual(text.analyze(short)[2], 3)
        self.assertTrue(short.endswith("..."))
        self.assertEqual(text.shorten("Habari", 3), "Habari")


class OutboundQueueTests(TestCase):
    def test_a_message_is_shaped_before_queueing(self):
        sms = outbox.send_sms("0712 345 678", "It’s  ready")
        self.assertEqual((sms.to, sms.body, sms.encoding, sms.parts, sms.status), (E164, "It's ready", "gsm7", 1, "queued"))
        self.assertGreater(sms.expires_at, timezone.now() + timedelta(hours=23))

    def test_nothing_is_queued_for_a_bad_number_an_empty_text_or_an_opted_out_person(self):
        self.assertIsNone(outbox.send_sms("MPESA", "hi"))
        self.assertIsNone(outbox.send_sms(SENDER, "   "))
        Contact.objects.create(phone=E164, opted_out=True)
        self.assertIsNone(outbox.send_sms(SENDER, "hi"))
        self.assertIsNotNone(outbox.send_sms(SENDER, "goodbye", force=True))


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False)
class AuthTests(GatewayBase):
    def test_ping_with_a_valid_token(self):
        response = self.api.get(self.url("ping"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["ok"], response.json()["device"]), (True, "office phone 1"))

    def test_the_call_marks_the_phone_as_seen(self):
        self.assertIsNone(Device.objects.get().last_seen)
        self.api.get(self.url("ping"))
        self.assertIsNotNone(Device.objects.get().last_seen)
        self.assertTrue(Device.objects.get().is_online)

    def test_no_token_a_wrong_token_and_a_wrong_scheme_are_401_in_our_error_format(self):
        for credentials in (None, "Bearer sgw_wrong", "Basic abc", "Bearer "):
            client = APIClient()
            if credentials:
                client.credentials(HTTP_AUTHORIZATION=credentials)
            response = client.get(self.url("ping"))
            self.assertEqual(response.status_code, 401, credentials)
            self.assertEqual(response.json()["error"]["code"], "invalid_token")

    def test_a_revoked_device_is_403(self):
        Device.objects.update(is_active=False)
        response = self.api.get(self.url("ping"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "device_disabled")

    def test_the_token_is_stored_only_as_a_hash(self):
        device = Device.objects.get()
        self.assertNotIn(self.token, (device.token_hash, device.token_prefix))
        self.assertTrue(self.token.startswith("sgw_"))
        self.assertEqual(device.token_prefix, self.token[:8])

    @override_settings(SMSGATEWAY_REQUIRE_HTTPS=True)
    def test_https_is_required_when_switched_on(self):
        response = self.api.get(self.url("ping"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "https_required")
        self.assertEqual(self.api.get(self.url("ping"), secure=True).status_code, 200)

    def test_an_app_older_than_the_minimum_gets_426(self):
        Device.objects.update(min_app_version="1.2.0")
        old = self.api.get(self.url("ping"), HTTP_X_APP_VERSION="1.1.9")
        self.assertEqual(old.status_code, 426)
        self.assertEqual(old.json()["error"]["code"], "upgrade_required")
        self.assertEqual(old.json()["error"]["min_app_version"], "1.2.0")
        self.assertEqual(self.api.get(self.url("ping"), HTTP_X_APP_VERSION="1.2.0").status_code, 200)
        self.assertEqual(self.api.get(self.url("ping"), HTTP_X_APP_VERSION="2.0.1").status_code, 200)
        self.assertEqual(self.api.get(self.url("ping")).status_code, 200)  # no version sent: not blocked

    def test_invalid_json_is_400(self):
        response = self.api.post(self.url("inbox"), "{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False)
class InboxTests(GatewayBase):
    def test_a_message_is_accepted_and_stored(self):
        message = self.message("BEI mbolea Arusha")
        response = self.upload(message)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual((result["client_id"], result["status"]), (message["client_id"], "accepted"))
        sms = InboundSms.objects.get()
        self.assertEqual((sms.sender, sms.body, sms.sim_slot, sms.parts, sms.device), (E164, "BEI mbolea Arusha", 0, 1, self.device))
        self.assertEqual(sms.sent_at.isoformat(), "2026-10-13T06:14:58+00:00")
        self.assertIn("server_time", response.json())

    def test_the_reply_is_never_in_the_upload_response(self):
        response = self.upload(self.message("msaada"))
        self.assertNotIn("reply", str(response.json()).lower().replace("replies", ""))
        self.assertTrue(OutboundSms.objects.exists())  # it is in the outbox instead

    def test_uploading_the_same_message_again_is_a_duplicate(self):
        message = self.message("msaada")
        first = self.upload(message).json()["results"][0]
        second = self.upload(message).json()["results"][0]
        self.assertEqual((second["status"], second["id"]), ("duplicate", first["id"]))
        self.assertEqual(InboundSms.objects.count(), 1)
        self.assertEqual(OutboundSms.objects.count(), 1)  # and it is not answered twice

    def test_the_same_client_id_from_two_phones_is_two_messages(self):
        other, _ = Device.issue("second phone")
        message = self.message("msaada", client_id="same-id")
        self.upload(message)
        InboundSms.objects.create(device=other, client_id="same-id", sender=E164, body="x")
        self.assertEqual(InboundSms.objects.filter(client_id="same-id").count(), 2)

    def test_a_batch_gets_one_result_each_in_order(self):
        good = self.message("msaada")
        no_id = {"from": SENDER, "body": "x"}
        no_from = {"client_id": "a1", "body": "x"}
        no_body = {"client_id": "a2", "from": SENDER}
        results = self.upload(good, no_id, no_from, no_body).json()["results"]
        self.assertEqual([r["status"] for r in results], ["accepted", "rejected", "rejected", "rejected"])
        self.assertEqual([r.get("reason") for r in results[1:]], ["missing_client_id", "missing_from", "missing_body"])

    def test_the_structure_is_checked(self):
        for body in ({}, {"messages": []}, {"messages": "x"}):
            response = self.api.post(self.url("inbox"), body, format="json")
            self.assertEqual(response.status_code, 422, body)
            self.assertEqual(response.json()["error"]["code"], "validation_failed")

    def test_more_than_fifty_is_413(self):
        response = self.upload(*[self.message("x") for _ in range(51)])
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "batch_too_large")
        self.assertFalse(InboundSms.objects.exists())

    def test_only_listed_senders_are_taken_when_the_server_says_so(self):
        Device.objects.update(allowed_senders=["0712345678"])
        results = self.upload(self.message("msaada"), self.message("msaada", sender="0755000111")).json()["results"]
        self.assertEqual([r["status"] for r in results], ["accepted", "rejected"])
        self.assertEqual(results[1]["reason"], "sender_not_allowed")

    def test_a_sender_name_like_mpesa_is_kept_but_never_answered(self):
        response = self.upload(self.message("You have received TSh 1,000", sender="MPESA"))
        self.assertEqual(response.json()["results"][0]["status"], "accepted")
        sms = InboundSms.objects.get()
        self.assertEqual((sms.sender, sms.status), ("MPESA", "ignored"))
        self.assertFalse(OutboundSms.objects.exists())

    def test_numbers_are_normalised_so_one_person_is_one_contact(self):
        self.upload(self.message("msaada", sender="0712 345 678"), self.message("msaada", sender="+255712345678"))
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(set(InboundSms.objects.values_list("sender", flat=True)), {E164})

    def test_unicode_survives_unchanged(self):
        body = "Majani yanageuka manjano – nifanye nini? é"
        self.upload(self.message(body))
        self.assertEqual(InboundSms.objects.get().body, body)


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False)
class OutboxTests(GatewayBase):
    def queue(self, body="Habari", to=SENDER, **kw):
        return outbox.send_sms(to, body, **kw)

    def fetch(self, **params):
        return self.api.get(self.url("outbox"), params).json()

    def test_the_phone_fetches_replies_in_order_and_they_are_leased(self):
        first, second = self.queue("one"), self.queue("two")
        data = self.fetch()
        self.assertEqual([m["id"] for m in data["messages"]], [first.pk, second.pk])
        message = data["messages"][0]
        self.assertEqual((message["to"], message["body"], message["encoding"], message["parts"]), (E164, "one", "gsm7", 1))
        self.assertIn("lease_expires_at", message)
        self.assertIn("expires_at", message)
        first.refresh_from_db()
        self.assertEqual((first.status, first.attempts, first.device), ("leased", 1, self.device))

    def test_a_leased_message_is_not_offered_again_straight_away(self):
        self.queue("one")
        self.fetch()
        self.assertEqual(self.fetch()["messages"], [])

    def test_a_lease_that_runs_out_puts_the_message_back(self):
        sms = self.queue("one")
        self.fetch()
        OutboundSms.objects.filter(pk=sms.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual([m["id"] for m in self.fetch()["messages"]], [sms.pk])
        sms.refresh_from_db()
        self.assertEqual(sms.attempts, 2)

    def test_the_limit_is_respected_and_capped(self):
        for i in range(25):
            self.queue(f"m{i}")
        self.assertEqual(len(self.fetch(limit=3)["messages"]), 3)
        self.assertEqual(len(self.fetch(limit=500)["messages"]), 20)
        self.assertEqual(len(self.fetch(limit="x")["messages"]), 2)  # 25 - 3 - 20 left; a bad limit falls back to 10

    def test_the_answer_says_how_long_to_wait(self):
        Device.objects.update(poll_interval_seconds=3, idle_poll_interval_seconds=12)
        self.assertEqual(self.fetch()["poll_after_seconds"], 12)  # nothing to do
        self.queue("one")
        self.assertEqual(self.fetch()["poll_after_seconds"], 3)  # there was work

    def test_old_messages_expire_instead_of_being_sent(self):
        sms = self.queue("late")
        OutboundSms.objects.filter(pk=sms.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.fetch()["messages"], [])
        sms.refresh_from_db()
        self.assertEqual(sms.status, "expired")

    def test_a_retry_delay_is_respected(self):
        sms = self.queue("later")
        OutboundSms.objects.filter(pk=sms.pk).update(available_at=timezone.now() + timedelta(minutes=5))
        self.assertEqual(self.fetch()["messages"], [])

    def test_higher_priority_goes_first(self):
        normal, urgent = self.queue("normal"), self.queue("urgent", priority=5)
        self.assertEqual([m["id"] for m in self.fetch()["messages"]], [urgent.pk, normal.pk])

    def test_a_message_pinned_to_another_phone_is_not_offered(self):
        other, _ = Device.issue("other phone")
        mine = self.queue("mine")
        theirs = self.queue("theirs", device=other)
        self.assertEqual([m["id"] for m in self.fetch()["messages"]], [mine.pk])
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, "queued")


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False)
class StatusTests(GatewayBase):
    def leased(self):
        sms = outbox.send_sms(SENDER, "Habari")
        self.api.get(self.url("outbox"))
        sms.refresh_from_db()
        return sms

    def report(self, sms, status, **extra):
        return self.api.post(self.url("outbox_status", pk=sms.pk), {"status": status, "at": "2026-10-13T09:15:09+03:00", "attempt": 1, **extra}, format="json")

    def test_sent_then_delivered(self):
        sms = self.leased()
        self.assertEqual(self.report(sms, "sent").json(), {"ok": True})
        sms.refresh_from_db()
        self.assertEqual(sms.status, "sent")
        self.assertIsNotNone(sms.sent_at)
        self.report(sms, "delivered")
        sms.refresh_from_db()
        self.assertEqual((sms.status, sms.delivered_at is not None), ("delivered", True))

    def test_reporting_twice_is_harmless_and_never_moves_backwards(self):
        sms = self.leased()
        self.report(sms, "sent")
        self.report(sms, "sent")
        self.report(sms, "delivered")
        self.report(sms, "sent")  # a late repeat of an old report
        self.report(sms, "failed", error="generic_failure", retryable=True)
        sms.refresh_from_db()
        self.assertEqual(sms.status, "delivered")

    def test_a_failure_worth_retrying_goes_back_in_the_queue_after_a_delay(self):
        sms = self.leased()
        self.report(sms, "failed", error="no_service", retryable=True)
        sms.refresh_from_db()
        self.assertEqual((sms.status, sms.last_error), ("queued", "no_service"))
        self.assertGreater(sms.available_at, timezone.now())
        self.assertEqual(self.api.get(self.url("outbox")).json()["messages"], [])  # not yet
        OutboundSms.objects.filter(pk=sms.pk).update(available_at=timezone.now())
        self.assertEqual(len(self.api.get(self.url("outbox")).json()["messages"]), 1)

    def test_a_permanent_failure_stays_failed(self):
        sms = self.leased()
        self.report(sms, "failed", error="invalid_number", retryable=False)
        sms.refresh_from_db()
        self.assertEqual((sms.status, sms.last_error), ("failed", "invalid_number"))

    def test_it_gives_up_after_too_many_attempts(self):
        sms = self.leased()
        OutboundSms.objects.filter(pk=sms.pk).update(attempts=OutboundSms.MAX_ATTEMPTS)
        sms.refresh_from_db()
        self.report(sms, "failed", error="no_service", retryable=True)
        sms.refresh_from_db()
        self.assertEqual(sms.status, "failed")

    def test_the_phone_can_report_that_it_let_one_expire(self):
        sms = self.leased()
        self.report(sms, "failed", error="expired", retryable=False)
        sms.refresh_from_db()
        self.assertEqual(sms.status, "expired")

    def test_unknown_or_another_phones_message_is_404(self):
        other, _ = Device.issue("other")
        theirs = outbox.send_sms(SENDER, "x", device=other)
        self.assertEqual(self.report(theirs, "sent").status_code, 404)
        self.assertEqual(self.api.post(self.url("outbox_status", pk=999999), {"status": "sent"}, format="json").status_code, 404)

    def test_a_bad_status_is_422(self):
        sms = self.leased()
        response = self.report(sms, "teleported")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_failed")

    def test_several_results_at_once(self):
        first = outbox.send_sms(SENDER, "one")
        second = outbox.send_sms(SENDER, "two")
        self.api.get(self.url("outbox"))
        response = self.api.post(self.url("outbox_status_batch"), {"results": [
            {"id": first.pk, "status": "sent"}, {"id": second.pk, "status": "failed", "error": "invalid_number"},
            {"id": 424242, "status": "sent"}, {"status": "sent"},
        ]}, format="json")
        results = response.json()["results"]
        self.assertEqual([r["ok"] for r in results], [True, True, False, False])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("sent", "failed"))
        self.assertEqual(self.api.post(self.url("outbox_status_batch"), {"results": []}, format="json").status_code, 422)


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False)
class HeartbeatTests(GatewayBase):
    BODY = {"app_version": "1.0.3", "android_sdk": 30, "battery_percent": 82, "charging": True, "network": "wifi", "signal": 3,
            "sim": {"slot": 0, "operator": "Vodacom Tanzania"}, "queue": {"inbox_waiting": 0, "outbox_waiting": 2}, "sent_today": 41}

    def test_it_records_the_phones_state_and_returns_our_settings(self):
        response = self.api.post(self.url("heartbeat"), self.BODY, format="json")
        self.assertEqual(response.status_code, 200)
        config = response.json()["config"]
        self.assertEqual((config["heartbeat_seconds"], config["send_interval_seconds"], config["daily_send_limit"], config["paused"]), (60, 4, 500, False))
        self.assertIsNone(config["allowed_senders"])
        device = Device.objects.get()
        self.assertEqual((device.battery_percent, device.charging, device.network, device.signal, device.sim_operator, device.app_version, device.sent_today),
                         (82, True, "wifi", 3, "Vodacom Tanzania", "1.0.3", 41))
        self.assertEqual(device.last_heartbeat["queue"]["outbox_waiting"], 2)
        self.assertTrue(device.is_online)

    def test_a_pause_set_by_staff_reaches_the_phone(self):
        Device.objects.update(paused=True, send_interval_seconds=9, allowed_senders=["+255712345678"])
        config = self.api.post(self.url("heartbeat"), self.BODY, format="json").json()["config"]
        self.assertEqual((config["paused"], config["send_interval_seconds"], config["allowed_senders"]), (True, 9, ["+255712345678"]))

    def test_nonsense_values_are_ignored_not_stored(self):
        self.api.post(self.url("heartbeat"), {**self.BODY, "battery_percent": 500, "charging": "yes", "signal": -4}, format="json")
        device = Device.objects.get()
        self.assertEqual((device.battery_percent, device.charging, device.signal), (None, None, None))

    def test_an_old_app_is_told_to_update_in_the_heartbeat_too(self):
        Device.objects.update(min_app_version="1.5.0")
        response = self.api.post(self.url("heartbeat"), self.BODY, format="json")
        self.assertEqual(response.status_code, 426)

    def test_a_phone_that_stops_reporting_goes_offline(self):
        self.api.post(self.url("heartbeat"), self.BODY, format="json")
        Device.objects.update(last_seen=timezone.now() - timedelta(minutes=10))
        self.assertFalse(Device.objects.get().is_online)


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False)
class HandlerTests(GatewayBase):
    def setUp(self):
        super().setUp()
        self.shop_user, self.shop = make_seller("0700000061", "agro_input_dealer", "Arusha Agrovet")
        self.shop.region = "Arusha"
        self.shop.phone_number = "0712000111"
        self.shop.save()

    def stock(self, name, price, quantity=5, shop=None, **extra):
        extra.setdefault("category", "fertilizer")
        return ShopStockItem.objects.create(shop=shop or self.shop, name=name, cost_price=1, selling_price=Decimal(price), quantity=Decimal(quantity), **extra)

    # help, language, stop
    def test_help_in_swahili_by_default(self):
        self.text_in("msaada")
        self.assertIn("SWALI", self.replies()[0])
        self.assertIn("BEI", self.replies()[0])

    def test_a_message_with_no_keyword_is_a_conversation_not_a_menu(self):
        sms = self.text_in("habari")
        self.assertEqual((sms.status, sms.handler), ("pending", "ask"))

    def test_an_empty_message_gets_help(self):
        sms = self.text_in(" ")
        self.assertEqual((sms.status, sms.handler), ("processed", "help"))

    @mock.patch("assistant.engine.chat_completion", return_value="Tuna Urea 46% TSh 70,000 Arusha Agrovet 0712 000 111. Uko mkoa gani?")
    def test_a_plain_request_is_answered_with_the_shops_in_stock(self, chat):
        self.stock("Urea 46%", 70000)
        self.stock("Maize seed 2kg", 10000, category="seeds")
        self.text_in("Nataka mbolea")
        services.process_pending()
        system = chat.call_args.args[0][0]["content"]
        self.assertIn("Urea 46%: TSh 70,000, Arusha Agrovet, Arusha, 0712 000 111", system)
        self.assertNotIn("Maize seed", system)
        self.assertIn("does not know any commands", system)
        self.assertIn("ask what they want to buy", system)
        self.assertIn("As soon as the farmer names what they want", system)
        self.assertIn("Urea 46%", self.replies()[0])

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_a_region_in_the_text_is_remembered_for_the_next_message(self, chat):
        self.stock("Urea 46%", 70000)
        self.text_in("Nataka mbolea Arusha")
        services.process_pending()
        self.assertEqual(Conversation.objects.get().region, "Arusha")
        self.text_in("na mbegu je")
        services.process_pending()
        self.assertIn("Urea", chat.call_args_list[0].args[0][0]["content"])
        self.assertEqual(Conversation.objects.get().region, "Arusha")

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_when_nothing_matches_the_assistant_is_told_so_and_not_given_other_regions_stock(self, chat):
        self.stock("Urea 46%", 70000)
        self.text_in("Nataka mbolea Kilimanjaro")
        services.process_pending()
        self.assertIn("none found for this message", chat.call_args.args[0][0]["content"])

    def test_language_can_be_changed_and_is_remembered(self):
        self.text_in("lugha en")
        self.assertEqual(self.replies()[-1], "Okay. I will reply in English.")
        self.text_in("help")
        self.assertIn("Send:", self.replies()[-1])
        self.text_in("LUGHA SW")
        self.assertEqual(self.replies()[-1], "Sawa. Nitajibu kwa Kiswahili.")
        self.assertEqual(Contact.objects.get().language, "sw")

    def test_an_unclear_language_gets_instructions(self):
        self.text_in("lugha kifaransa")
        self.assertIn("LUGHA SW", self.replies()[0])

    def test_stop_stops_everything_until_start(self):
        self.text_in("stop")
        self.assertEqual(Contact.objects.get().opted_out, True)
        self.assertIn("Umejiondoa", self.replies()[0])  # the confirmation is allowed through
        count = OutboundSms.objects.count()
        sms = self.text_in("BEI mbolea")
        self.assertEqual((sms.status, sms.note), ("ignored", "opted out"))
        self.assertEqual(OutboundSms.objects.count(), count)
        self.assertIsNone(outbox.send_sms(SENDER, "a reminder"))  # nothing else can reach them either
        self.text_in("start")
        self.assertFalse(Contact.objects.get().opted_out)
        self.assertIn("Karibu tena", self.replies()[-1])
        self.assertIsNotNone(outbox.send_sms(SENDER, "now allowed"))

    def test_a_person_who_opted_out_can_still_ask_for_help(self):
        self.text_in("stop")
        self.text_in("msaada")
        self.assertIn("SWALI", self.replies()[-1])

    # prices and shops
    def test_price_finds_the_item_with_its_shop_and_number(self):
        self.stock("CAN fertilizer 50kg", 62000)
        self.text_in("BEI CAN Arusha")
        self.assertEqual(self.replies()[0], "CAN fertilizer 50kg: TSh 62,000, Arusha Agrovet 0712 000 111")

    def test_swahili_product_words_match_the_category(self):
        self.stock("Urea 46%", 70000)
        self.stock("Maize seed 2kg", 10000, category="seeds")
        self.text_in("bei mbolea")
        reply = self.replies()[0]
        self.assertIn("Urea 46%", reply)
        self.assertNotIn("Maize seed", reply)

    def test_the_region_narrows_the_search(self):
        other_user, moshi = make_seller("0700000062", "agro_input_dealer", "Moshi Agrovet")
        moshi.region = "Kilimanjaro"
        moshi.phone_number = "0713000222"
        moshi.save()
        self.stock("Urea 46%", 70000)
        self.stock("Urea 46%", 68000, shop=moshi)
        self.text_in("BEI urea Kilimanjaro")
        self.assertEqual(self.replies()[0], "Urea 46%: TSh 68,000, Moshi Agrovet 0713 000 222")
        self.text_in("BEI urea")
        self.assertEqual(self.replies()[1].count("\n"), 1)  # both shops, cheapest first
        self.assertTrue(self.replies()[1].startswith("Urea 46%: TSh 68,000"))

    def test_only_three_results_the_cheapest_first(self):
        for i, price in enumerate((9000, 5000, 7000, 6000, 8000)):
            self.stock(f"Seed pack {i}", price, category="seeds")
        self.text_in("bei seed")
        lines = self.replies()[0].split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual([line.split(": ")[1].rsplit(",", 1)[0] if False else line.split(": ")[1].split(", ")[0] for line in lines], ["TSh 5,000", "TSh 6,000", "TSh 7,000"])

    def test_things_that_cannot_be_sold_are_not_offered(self):
        self.stock("Sold out urea", 1000, quantity=0)
        self.stock("Expired urea", 1000, expiry_date=timezone.localdate() - timedelta(days=1))
        self.stock("Hidden urea", 1000, is_active=False)
        off_user, off = make_seller("0700000063", "agro_input_dealer", "Closed Agrovet")
        off.is_active = False
        off.save()
        self.stock("Closed shop urea", 1000, shop=off)
        self.text_in("bei urea")
        self.assertIn("Hatukupata", self.replies()[0])

    def test_nothing_found_and_nothing_asked(self):
        self.text_in("bei trekta")
        self.assertIn("Hatukupata trekta", self.replies()[0])
        self.text_in("bei")
        self.assertIn("Andika bidhaa", self.replies()[1])
        self.text_in("bei Arusha")
        self.assertIn("Andika bidhaa", self.replies()[2])

    def test_prices_in_english(self):
        self.stock("Urea 46%", 70000)
        self.text_in("lugha en")
        self.text_in("bei trekta Arusha")
        self.assertEqual(self.replies()[-1], "We found no shop with trekta in Arusha in stock. Try another name or region.")

    # order status
    def test_status_of_a_website_order_only_for_the_phone_that_placed_it(self):
        buyer = self.shop_user
        order = Order.objects.create(user=buyer, total_amount=1000, shipping_address="x", phone_number=SENDER, status="processing")
        self.text_in(f"HALI {order.pk}")
        self.assertEqual(self.replies()[0], f"Oda #{order.pk}: inaandaliwa.")
        self.text_in(f"HALI {order.pk}", sender="0755999888")
        self.assertIn("Hatukupata oda", self.replies(to="+255755999888")[0])  # someone else's number sees nothing

    def test_status_of_a_kikapu_order_by_ms_number_or_its_own_id(self):
        order = FarmerOrder.objects.create(
            shop=self.shop, external_order_id="KP-INP-00482", farmer_name="Niko", farmer_phone="+255712345678", status="dispatched",
            shop_note="Rider arrives today",
        )
        self.text_in(f"hali {order.order_number}")
        self.assertEqual(self.replies()[0], f"Oda {order.order_number}: imetumwa. Rider arrives today")
        self.text_in("hali KP-INP-00482")
        self.assertEqual(self.replies()[1], self.replies()[0])

    def test_status_with_no_number_is_the_latest_order(self):
        FarmerOrder.objects.create(shop=self.shop, external_order_id="KP-1", farmer_name="N", farmer_phone=E164, status="delivered")
        self.text_in("hali")
        self.assertIn("imefika", self.replies()[0])

    def test_status_when_there_is_no_order(self):
        self.text_in("hali")
        self.assertIn("Hatuna oda", self.replies()[0])
        self.text_in("hali 99999")
        self.assertIn("Hatukupata oda", self.replies()[1])

    # questions
    @mock.patch("assistant.engine.chat_completion", return_value="**Majani ya njano** mara nyingi ni upungufu wa nitrojeni.\n- Weka mbolea ya CAN\n- Tuma swali tena kwa maelezo zaidi")
    def test_a_question_waits_for_the_worker_then_is_answered_in_plain_short_text(self, chat):
        sms = self.text_in("SWALI majani ya mahindi yanageuka manjano nifanye nini")
        self.assertEqual((sms.status, sms.handler), ("pending", "ask"))
        self.assertEqual(self.replies(), [])  # the phone's upload was not held up
        counts = services.process_pending()
        self.assertEqual(counts["answered"], 1)
        sms.refresh_from_db()
        self.assertEqual(sms.status, "processed")
        reply = self.replies()[0]
        self.assertNotIn("*", reply)
        self.assertIn("Majani ya njano", reply)
        self.assertLessEqual(text.analyze(reply)[2], 3)
        conversation = Conversation.objects.get()
        self.assertEqual((conversation.channel, conversation.phone_number, conversation.language), ("sms", E164, "sw"))
        system = chat.call_args.args[0][0]["content"]
        self.assertIn("at most 300 characters", system)

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_a_long_message_with_no_keyword_is_treated_as_a_question(self, _):
        sms = self.text_in("majani ya mahindi yangu yanageuka manjano kila siku")
        self.assertEqual(sms.handler, "ask")
        services.process_pending()
        self.assertEqual(self.replies(), ["ok"])

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_the_same_question_is_not_answered_twice(self, _):
        self.text_in("SWALI majani ya mahindi yanageuka manjano")
        services.process_pending()
        services.process_pending()
        self.assertEqual(len(self.replies()), 1)

    @mock.patch("assistant.engine.chat_completion", side_effect=DiagnosisError("down", status=502))
    def test_when_the_assistant_is_down_the_farmer_gets_an_apology_not_silence(self, _):
        self.text_in("SWALI majani ya mahindi yanageuka manjano")
        services.process_pending()
        self.assertIn("Samahani", self.replies()[0])

    @mock.patch("assistant.engine.chat_completion", side_effect=RuntimeError("boom"))
    def test_a_crash_is_retried_a_few_times_then_given_up_on(self, _):
        sms = self.text_in("SWALI majani ya mahindi yanageuka manjano")
        for _ in range(4):
            services.process_pending()
        sms.refresh_from_db()
        self.assertEqual(sms.status, "ignored")
        self.assertIn("gave up", sms.note)
        self.assertEqual(self.replies(), [])

    def test_too_many_messages_in_an_hour_are_ignored(self):
        for i in range(services.SENDER_LIMIT_PER_HOUR + 1):
            self.text_in("msaada")
        last = InboundSms.objects.latest("id")
        self.assertEqual((last.status, last.note), ("ignored", "too many messages this hour"))
        self.assertEqual(len(self.replies()), services.SENDER_LIMIT_PER_HOUR)

    def test_a_project_with_no_handlers_ignores_messages_safely(self):
        Device.objects.update(project="school")
        sms = self.text_in("matokeo 123")
        self.assertEqual((sms.status, sms.note), ("ignored", "no handler for project school"))

    def test_a_crash_in_a_quick_handler_does_not_fail_the_upload_and_is_retried(self):
        with mock.patch.dict("smsgateway.handlers.PROJECTS", {"mkulima": {**__import__("smsgateway.handlers", fromlist=["PROJECTS"]).PROJECTS["mkulima"], "handlers": {
            **__import__("smsgateway.handlers", fromlist=["PROJECTS"]).PROJECTS["mkulima"]["handlers"], "help": mock.Mock(side_effect=RuntimeError("boom"))}}}):
            response = self.upload(self.message("msaada"))
        self.assertEqual(response.json()["results"][0]["status"], "accepted")
        sms = InboundSms.objects.get()
        self.assertEqual((sms.status, sms.attempts), ("pending", 1))
        services.process_pending()  # the real handler now works
        sms.refresh_from_db()
        self.assertEqual(sms.status, "processed")


@override_settings(SMSGATEWAY_REQUIRE_HTTPS=False, CALLCENTER_ENABLED=True, KIKAPU_BRIDGE_REPLY_URL="https://kikapu.test/replies/")
class CallCenterOverSmsTests(GatewayBase):
    """An SMS question can be answered by a human agronomist; the answer goes back as an SMS, not WhatsApp."""

    def setUp(self):
        super().setUp()
        self.owner, self.company = make_seller("0712000001", "manufacturer", "Zamseed Tanzania")
        self.agronomist = make_agronomist("asha@zamseed.test", self.company)

    def ask(self):
        sms = self.text_in("SWALI majani ya mahindi yanageuka manjano nifanye nini")
        services.process_pending()
        sms.refresh_from_db()
        return sms

    @mock.patch("assistant.engine.chat_completion", return_value="AI answer")
    def test_with_an_agronomist_online_the_farmer_is_told_one_is_coming(self, chat):
        self.ask()
        self.assertEqual(Case.objects.get().status, "waiting")
        self.assertIn("mtaalamu wa kilimo", self.replies()[0])
        chat.assert_not_called()  # the AI stays quiet while a person may answer

    @mock.patch("assistant.engine.chat_completion", return_value="AI answer")
    def test_the_agronomists_answer_goes_back_by_sms_with_their_name(self, _):
        self.ask()
        case = Case.objects.get()
        callcenter.accept(case.pk, self.agronomist)
        callcenter.reply(case.pk, self.agronomist, "Weka mbolea ya CAN wiki hii.")
        self.assertEqual(self.replies()[-1], "Weka mbolea ya CAN wiki hii.\n\n- Asha Mwakyusa, Zamseed Tanzania")
        self.assertFalse(ReplyDelivery.objects.exists())  # not a WhatsApp message

    @mock.patch("assistant.engine.chat_completion", return_value="**Jibu la AI** kwa swali lako.")
    def test_when_nobody_takes_it_the_ai_answers_by_sms_in_plain_text(self, _):
        self.ask()
        Agronomist.objects.update(is_available=False)
        callcenter.sweep()
        self.assertEqual(self.replies()[-1], "Jibu la AI kwa swali lako.")
        self.assertFalse(ReplyDelivery.objects.exists())

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_the_background_worker_answers_waiting_sms(self, _):
        Agronomist.objects.update(is_available=False)
        self.text_in("SWALI majani ya mahindi yanageuka manjano")
        self.assertEqual(self.replies(), [])
        call_command("run_callcenter")
        self.assertEqual(self.replies(), ["ok"])

    def test_the_worker_also_expires_old_unsent_replies(self):
        sms = outbox.send_sms(SENDER, "late")
        OutboundSms.objects.filter(pk=sms.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        call_command("run_callcenter")
        sms.refresh_from_db()
        self.assertEqual(sms.status, "expired")


class IssueDeviceCommandTests(TestCase):
    def test_the_command_creates_a_device_and_prints_its_token_once(self):
        from io import StringIO

        out = StringIO()
        call_command("issue_sms_device", "sandbox", "--project", "mkulima", stdout=out)
        device = Device.objects.get(name="sandbox")
        token = [line for line in out.getvalue().splitlines() if line.startswith("sgw_")][0]
        self.assertEqual(device.token_prefix, token[:8])
        self.assertEqual(device.project, "mkulima")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        with override_settings(SMSGATEWAY_REQUIRE_HTTPS=False):
            self.assertEqual(client.get("/api/sms-gateway/v1/ping/").status_code, 200)

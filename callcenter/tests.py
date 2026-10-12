import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from assistant.models import Conversation, Message
from assistant.tests import PHONE, AssistantTestBase, diagnosis_answer, photo
from inputs.tests import make_seller
from kikapu_bridge.models import ReplyDelivery
from kikapu_bridge.webhooks import deliver_replies

from . import services
from .models import Agronomist, Case, Invite

User = get_user_model()

REPLY_URL = "https://kikapu.test/api/kikapu-bridge/assistant/replies/"
SECRET = "reply-secret"
AI_TEXT = "Hii ni jibu la AI."


def make_agronomist(email, company=None, online=True, name="Asha Mwakyusa"):
    user = User.objects.create_user(password="pass12345", email=email)
    agronomist = Agronomist.objects.create(
        user=user, company=company, full_name=name, is_available=online, last_seen=timezone.now() if online else None,
    )
    return agronomist


@override_settings(CALLCENTER_ENABLED=True, KIKAPU_BRIDGE_REPLY_URL=REPLY_URL, KIKAPU_BRIDGE_WEBHOOK_SECRET=SECRET)
class CallcenterBase(AssistantTestBase):
    def setUp(self):
        super().setUp()
        self.owner, self.company = make_seller("0712000001", "manufacturer", "Zamseed Tanzania")
        self.agronomist = make_agronomist("asha@zamseed.test", self.company)

    def conversation(self):
        return Conversation.objects.get(phone_number=PHONE)

    def case(self):
        return Case.objects.get(conversation=self.conversation())

    def start_case(self, message_id="m1", text="My maize leaves are yellow"):
        body = self.send(text=text, language="en", message_id=message_id).json()
        return body


class RoutingTests(CallcenterBase):
    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_nobody_online_the_ai_answers_straight_away(self, _):
        Agronomist.objects.update(is_available=False)
        body = self.start_case()
        self.assertEqual(body["reply"]["text"], AI_TEXT)
        self.assertFalse(body["queued"])
        self.assertEqual(Case.objects.count(), 0)

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_agronomist_who_stopped_polling_is_not_online(self, _):
        Agronomist.objects.update(last_seen=timezone.now() - timedelta(minutes=5))
        body = self.start_case()
        self.assertEqual(body["reply"]["text"], AI_TEXT)
        self.assertEqual(Case.objects.count(), 0)

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_an_agronomist_online_gets_the_chat_and_the_farmer_an_acknowledgement(self, chat):
        body = self.start_case()
        self.assertTrue(body["queued"])
        self.assertIn("connecting you to an agronomist", body["reply"]["text"])
        self.assertEqual(self.case().status, Case.WAITING)
        chat.assert_not_called()  # the AI stays quiet while a person may answer

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_further_messages_while_waiting_get_no_second_acknowledgement(self, _):
        self.start_case("m1")
        body = self.start_case("m2", text="It started last week")
        self.assertTrue(body["queued"])
        self.assertEqual(body["reply"]["text"], "")
        self.assertEqual(Case.objects.count(), 1)

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_call_center_off_changes_nothing(self, _):
        with override_settings(CALLCENTER_ENABLED=False):
            body = self.start_case()
        self.assertEqual(body["reply"]["text"], AI_TEXT)
        self.assertEqual(Case.objects.count(), 0)

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    def test_a_photo_is_kept_for_the_agronomist_and_validated_on_arrival(self, diagnose):
        body = self.send(image=photo(), language="en", message_id="p1").json()
        self.assertTrue(body["queued"])
        diagnose.assert_not_called()
        self.assertTrue(Message.objects.get(external_id="p1").photo)
        bad = self.send(image=SimpleUploadedFile("x.png", b"not an image", content_type="image/png"), language="en", message_id="p2")
        self.assertEqual(bad.status_code, 400)


class AgronomistTests(CallcenterBase):
    def setUp(self):
        super().setUp()
        self.start_case("m1")
        self.case_id = self.case().pk

    def test_only_the_first_to_accept_gets_the_chat(self):
        other = make_agronomist("juma@seeds.test", name="Juma")
        self.assertTrue(services.accept(self.case_id, self.agronomist))
        self.assertFalse(services.accept(self.case_id, other))
        self.assertEqual(self.case().agronomist, self.agronomist)

    def test_reply_is_stored_signed_and_queued_for_kikapu(self):
        services.accept(self.case_id, self.agronomist)
        message = services.reply(self.case_id, self.agronomist, "Spray early in the morning.")
        self.assertEqual(message.role, "agronomist")
        delivery = ReplyDelivery.objects.get()
        self.assertEqual(delivery.payload["source"], "agronomist")
        self.assertEqual(delivery.payload["phone_number"], PHONE)
        self.assertEqual(delivery.payload["reply_id"], f"MSR-{message.pk}")
        self.assertIn("Spray early in the morning.", delivery.payload["text"])
        self.assertIn("- Asha Mwakyusa, Zamseed Tanzania", delivery.payload["text"])

    def test_reply_is_posted_to_kikapu_with_a_valid_signature(self):
        services.accept(self.case_id, self.agronomist)
        services.reply(self.case_id, self.agronomist, "Hello from Zamseed")
        with mock.patch("kikapu_bridge.webhooks.requests.post", return_value=mock.Mock(status_code=200, text="ok")) as post:
            self.assertEqual(deliver_replies(), (1, 0))
        self.assertEqual(post.call_args.args[0], REPLY_URL)
        body = post.call_args.kwargs["data"]
        headers = post.call_args.kwargs["headers"]
        expected = hmac.new(SECRET.encode(), f"{headers['X-Webhook-Timestamp']}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-Webhook-Signature"], expected)
        self.assertEqual(json.loads(body)["event"], "assistant.reply")
        self.assertIsNotNone(ReplyDelivery.objects.get().delivered_at)

    def test_failed_delivery_is_retried_later_and_keeps_order(self):
        services.accept(self.case_id, self.agronomist)
        services.reply(self.case_id, self.agronomist, "first")
        services.reply(self.case_id, self.agronomist, "second")
        with mock.patch("kikapu_bridge.webhooks.requests.post", return_value=mock.Mock(status_code=503, text="down")) as post:
            self.assertEqual(deliver_replies(), (0, 1))
        self.assertEqual(post.call_count, 1)  # "second" waits behind "first"
        with mock.patch("kikapu_bridge.webhooks.requests.post", return_value=mock.Mock(status_code=200, text="ok")) as post:
            self.assertEqual(deliver_replies(now=timezone.now() + timedelta(minutes=5)), (2, 0))
        sent = [json.loads(c.kwargs["data"])["text"] for c in post.call_args_list]
        self.assertTrue(sent[0].startswith("first") and sent[1].startswith("second"))

    def test_nobody_else_can_reply_to_a_chat_that_is_not_theirs(self):
        other = make_agronomist("juma@seeds.test", name="Juma")
        with self.assertRaises(PermissionDenied):
            services.reply(self.case_id, other, "mine now")
        services.accept(self.case_id, self.agronomist)
        with self.assertRaises(PermissionDenied):
            services.reply(self.case_id, other, "mine now")

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_farmer_follow_ups_stay_with_the_agronomist(self, chat):
        services.accept(self.case_id, self.agronomist)
        body = self.start_case("m2", text="How much do I use?")
        self.assertTrue(body["queued"])
        self.assertEqual(body["reply"]["text"], "")
        chat.assert_not_called()

    def test_release_puts_the_chat_back_in_the_queue(self):
        services.accept(self.case_id, self.agronomist)
        services.release(self.case_id, self.agronomist)
        case = self.case()
        self.assertEqual((case.status, case.agronomist), (Case.WAITING, None))

    def test_close_ends_the_chat_and_the_next_message_starts_a_new_case(self):
        services.accept(self.case_id, self.agronomist)
        services.close(self.case_id, self.agronomist)
        self.start_case("m3", text="Another question")
        self.assertEqual(Case.objects.count(), 2)

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_agronomist_can_hand_the_chat_to_the_ai(self, _):
        services.accept(self.case_id, self.agronomist)
        self.assertTrue(services.hand_to_ai(self.case_id, self.agronomist))
        self.assertEqual(self.case().status, Case.AI)
        self.assertEqual(ReplyDelivery.objects.get().payload["source"], "ai")


class SweepTests(CallcenterBase):
    def setUp(self):
        super().setUp()
        self.start_case("m1")

    def sweep_in(self, seconds):
        return services.sweep(now=timezone.now() + timedelta(seconds=seconds))

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_ai_waits_the_full_time_when_an_agronomist_is_online(self, chat):
        Agronomist.objects.update(last_seen=timezone.now() + timedelta(hours=1))  # stays online through the sweep
        self.assertEqual(self.sweep_in(60)["ai"], 0)
        chat.assert_not_called()
        self.assertEqual(self.case().status, Case.WAITING)

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_ai_answers_when_nobody_accepts_in_time(self, chat):
        Agronomist.objects.update(last_seen=timezone.now() + timedelta(hours=1))
        self.assertEqual(self.sweep_in(121)["ai"], 1)
        case = self.case()
        self.assertEqual(case.status, Case.AI)
        self.assertTrue(case.answered_by_ai)
        delivery = ReplyDelivery.objects.get()
        self.assertEqual((delivery.payload["source"], delivery.payload["text"]), ("ai", AI_TEXT))

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_ai_answers_at_once_if_everyone_goes_offline(self, _):
        Agronomist.objects.update(is_available=False)
        self.assertEqual(self.sweep_in(5)["ai"], 1)

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    def test_ai_diagnoses_a_photo_that_was_waiting(self, diagnose):
        Conversation.objects.all().delete()
        self.send(image=photo(), language="en", message_id="p1")
        Agronomist.objects.update(is_available=False)
        services.sweep()
        diagnose.assert_called_once()
        self.assertIn("Fall armyworm", ReplyDelivery.objects.get().payload["text"])

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_after_the_ai_answers_it_keeps_the_chat_for_a_while(self, chat):
        Agronomist.objects.update(is_available=False)
        services.sweep()
        Agronomist.objects.update(is_available=True, last_seen=timezone.now())
        body = self.start_case("m2", text="And the second spray?")
        self.assertEqual(body["reply"]["text"], AI_TEXT)  # no new wait
        self.assertFalse(body["queued"])

    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_an_agronomist_can_take_over_from_the_ai(self, _):
        Agronomist.objects.update(is_available=False)
        services.sweep()
        self.assertTrue(services.accept(self.case().pk, self.agronomist))
        self.assertEqual(self.case().status, Case.OPEN)

    def test_an_agronomist_who_goes_quiet_loses_the_chat(self):
        services.accept(self.case().pk, self.agronomist)
        Agronomist.objects.update(last_seen=timezone.now() + timedelta(hours=1))
        self.assertEqual(self.sweep_in(601)["released"], 1)
        case = self.case()
        self.assertEqual((case.status, case.agronomist), (Case.WAITING, None))

    def test_an_agronomist_who_replied_keeps_the_chat(self):
        services.accept(self.case().pk, self.agronomist)
        services.reply(self.case().pk, self.agronomist, "Checking")
        self.assertEqual(self.sweep_in(3000)["released"], 0)


class ConsoleViewTests(CallcenterBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.agronomist.user)
        self.start_case("m1")
        self.case_id = self.case().pk

    def test_state_lists_waiting_chats_and_marks_the_agronomist_seen(self):
        Agronomist.objects.update(last_seen=timezone.now() - timedelta(minutes=10))
        data = self.client.get(reverse("callcenter:state")).json()
        self.assertEqual([c["id"] for c in data["waiting"]], [self.case_id])
        self.assertNotIn(PHONE, json.dumps(data))  # the farmer's number is masked
        self.assertTrue(Agronomist.objects.get().is_online or self.agronomist.is_available)
        self.assertGreater(Agronomist.objects.get().last_seen, timezone.now() - timedelta(minutes=1))

    def test_going_online_and_offline(self):
        self.client.post(reverse("callcenter:availability"), {"available": "0"})
        self.assertFalse(Agronomist.objects.get().is_available)
        self.client.post(reverse("callcenter:availability"), {"available": "1"})
        self.assertTrue(Agronomist.objects.get().is_available)

    def test_accept_then_reply_through_the_pages(self):
        accepted = self.client.post(reverse("callcenter:case_accept", args=[self.case_id]))
        self.assertEqual(accepted.status_code, 200)
        reply = self.client.post(reverse("callcenter:case_reply", args=[self.case_id]), {"text": "Try Duduthrin"})
        self.assertEqual(reply.status_code, 200)
        messages = self.client.get(reverse("callcenter:case_messages", args=[self.case_id])).json()
        self.assertTrue(messages["mine"])
        self.assertEqual(messages["messages"][-1]["text"], "Try Duduthrin")
        self.assertEqual(self.client.get(reverse("callcenter:case", args=[self.case_id])).status_code, 200)

    def test_second_agronomist_gets_a_conflict_not_the_chat(self):
        self.client.post(reverse("callcenter:case_accept", args=[self.case_id]))
        other = make_agronomist("juma@seeds.test", name="Juma")
        second = Client()
        second.force_login(other.user)
        self.assertEqual(second.post(reverse("callcenter:case_accept", args=[self.case_id])).status_code, 409)
        self.assertEqual(second.get(reverse("callcenter:case", args=[self.case_id])).status_code, 403)
        self.assertEqual(second.post(reverse("callcenter:case_reply", args=[self.case_id]), {"text": "x"}).status_code, 403)

    def test_an_empty_reply_is_rejected(self):
        self.client.post(reverse("callcenter:case_accept", args=[self.case_id]))
        self.assertEqual(self.client.post(reverse("callcenter:case_reply", args=[self.case_id]), {"text": "  "}).status_code, 400)

    def test_someone_who_is_not_an_agronomist_is_turned_away(self):
        client = Client()
        client.force_login(User.objects.create_user(password="pass12345", email="farmer@x.test"))
        self.assertEqual(client.get(reverse("callcenter:console")).status_code, 403)
        self.assertEqual(client.get(reverse("callcenter:state")).status_code, 403)

    def test_a_switched_off_agronomist_is_turned_away(self):
        Agronomist.objects.update(is_active=False)
        self.assertEqual(self.client.get(reverse("callcenter:console")).status_code, 403)

    def test_signed_out_visitors_go_to_the_login(self):
        response = Client().get(reverse("callcenter:console"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])


class TeamAndInviteTests(CallcenterBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.owner)

    def make_invite(self, **fields):
        return Invite.objects.create(company=self.company, **fields)

    def test_company_creates_an_invite_and_sees_the_link(self):
        self.client.post(reverse("callcenter:team_invite"), {"name": "Neema"})
        invite = Invite.objects.get()
        page = self.client.get(reverse("callcenter:team"))
        self.assertContains(page, reverse("callcenter:join", args=[invite.token]))
        self.assertContains(page, "Neema")

    def test_only_a_business_account_can_open_the_team_page(self):
        client = Client()
        client.force_login(User.objects.create_user(password="pass12345", email="nobody@x.test"))
        self.assertEqual(client.get(reverse("callcenter:team")).status_code, 302)

    def test_invite_link_creates_a_login_for_that_company(self):
        invite = self.make_invite(name="Neema")
        guest = Client()
        page = guest.get(reverse("callcenter:join", args=[invite.token]))
        self.assertContains(page, "Zamseed Tanzania")
        response = guest.post(reverse("callcenter:join", args=[invite.token]), {
            "full_name": "Neema Joseph", "email": "Neema@Zamseed.test", "password": "Str0ng-pass-99", "password2": "Str0ng-pass-99",
        })
        self.assertRedirects(response, reverse("callcenter:console"), fetch_redirect_response=False)
        agronomist = Agronomist.objects.get(user__email="neema@zamseed.test")
        self.assertEqual(agronomist.company, self.company)
        self.assertFalse(agronomist.is_available)  # she switches herself on
        self.assertEqual(guest.get(reverse("callcenter:console")).status_code, 200)  # already signed in
        invite.refresh_from_db()
        self.assertEqual(invite.agronomist, agronomist)

    def test_an_invite_works_only_once(self):
        invite = self.make_invite()
        data = {"full_name": "A B", "email": "a@x.test", "password": "Str0ng-pass-99", "password2": "Str0ng-pass-99"}
        Client().post(reverse("callcenter:join", args=[invite.token]), data)
        again = Client().post(reverse("callcenter:join", args=[invite.token]), {**data, "email": "b@x.test"})
        self.assertEqual(again.status_code, 410)
        self.assertFalse(User.objects.filter(email="b@x.test").exists())

    def test_expired_and_unknown_links_do_not_work(self):
        invite = self.make_invite(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(Client().get(reverse("callcenter:join", args=[invite.token])).status_code, 410)
        self.assertEqual(Client().get(reverse("callcenter:join", args=["nope"])).status_code, 410)

    def test_join_rejects_a_taken_email_and_weak_or_mismatched_passwords(self):
        invite = self.make_invite()
        url = reverse("callcenter:join", args=[invite.token])
        taken = Client().post(url, {"full_name": "A", "email": "asha@zamseed.test", "password": "Str0ng-pass-99", "password2": "Str0ng-pass-99"})
        self.assertContains(taken, "already exists")
        mismatch = Client().post(url, {"full_name": "A", "email": "c@x.test", "password": "Str0ng-pass-99", "password2": "other"})
        self.assertContains(mismatch, "do not match")
        weak = Client().post(url, {"full_name": "A", "email": "c@x.test", "password": "12345678", "password2": "12345678"})
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(Agronomist.objects.filter(user__email="c@x.test").exists())

    def test_cancelling_an_invite(self):
        invite = self.make_invite()
        self.client.post(reverse("callcenter:team_revoke", args=[invite.pk]))
        self.assertFalse(Invite.objects.exists())

    def test_one_company_cannot_touch_anothers_agronomist(self):
        other_owner, other_company = make_seller("0712000002", "agro_input_dealer", "Other Agrovet")
        client = Client()
        client.force_login(other_owner)
        client.post(reverse("callcenter:team_toggle", args=[self.agronomist.pk]))
        self.assertTrue(Agronomist.objects.get(pk=self.agronomist.pk).is_active)

    def test_switching_an_agronomist_off_returns_their_chats_to_the_queue(self):
        self.start_case("m1")
        services.accept(self.case().pk, self.agronomist)
        self.client.post(reverse("callcenter:team_toggle", args=[self.agronomist.pk]))
        agronomist = Agronomist.objects.get()
        self.assertFalse(agronomist.is_active or agronomist.is_available)
        self.assertEqual(self.case().status, Case.WAITING)


class WorkerCommandTests(CallcenterBase):
    @mock.patch("assistant.engine.chat_completion", return_value=AI_TEXT)
    def test_one_round_hands_over_and_sends(self, _):
        self.start_case("m1")
        Agronomist.objects.update(is_available=False)
        with mock.patch("kikapu_bridge.webhooks.requests.post", return_value=mock.Mock(status_code=200, text="ok")) as post:
            call_command("run_callcenter")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.case().status, Case.AI)
        self.assertIsNotNone(ReplyDelivery.objects.get().delivered_at)


class AgrovetAndSupplierTests(CallcenterBase):
    def setUp(self):
        super().setUp()
        self.shop_owner, self.shop = make_seller("0712000009", "agro_input_dealer", "Mama Neema Agrovet")
        self.seedling_owner, self.seedling = make_seller("0712000010", "seedling_seller", "Green Seedlings")
        self.nursery_owner, self.nursery = make_seller("0712000011", "nursery_operator", "Kilimo Nursery")

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_manufacturers_producers_and_suppliers_get_the_agronomist_page(self):
        for owner in (self.owner, self.seedling_owner, self.nursery_owner):
            client = self.login(owner)
            self.assertEqual(client.get(reverse("callcenter:team")).status_code, 200, owner.phone_number)
            client.post(reverse("callcenter:team_invite"), {"name": "Neema"})
        self.assertEqual(Invite.objects.count(), 3)

    def test_agrovets_do_not_get_it_and_are_told_why(self):
        client = self.login(self.shop_owner)
        response = client.get(reverse("callcenter:team"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("inputs:shop_dashboard"))
        self.assertContains(response, "Agronomists are for manufacturers and suppliers")

    def test_an_agrovet_cannot_invite_anyone_by_posting_directly(self):
        client = self.login(self.shop_owner)
        client.post(reverse("callcenter:team_invite"), {"name": "Neema"})
        self.assertFalse(Invite.objects.filter(company=self.shop).exists())

    def test_agrovets_have_the_pos_stock_and_stock_requests_but_no_agronomists_tab(self):
        page = self.login(self.shop_owner).get(reverse("inputs:shop_dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, reverse("callcenter:team"))
        self.assertNotContains(page, "Your agronomists")
        self.assertContains(page, reverse("inputs:pos"))
        self.assertContains(page, reverse("inputs:stock_list"))
        self.assertContains(page, "Request Stock")
        self.assertContains(page, "My Stock Requests")
        self.assertContains(page, reverse("inputs:catalog"))  # where stock is requested from suppliers

    def test_suppliers_see_the_tab_and_an_invitation_on_their_dashboard(self):
        manufacturer = self.login(self.owner).get(reverse("inputs:manufacturer_dashboard"))
        self.assertContains(manufacturer, reverse("callcenter:team"))
        self.assertContains(manufacturer, "Manage agronomists")  # setUp already gave this company an agronomist
        self.assertContains(manufacturer, "1 agronomist can answer farmers")
        seedling = self.login(self.seedling_owner).get(reverse("inputs:shop_dashboard"))
        self.assertContains(seedling, reverse("callcenter:team"))
        self.assertContains(seedling, "Invite agronomists")

    def test_the_seller_type_is_called_agrovet_in_registration(self):
        from website.forms import FarmerRegistrationForm

        labels = dict(FarmerRegistrationForm().fields["supplier_seller_type"].choices)
        self.assertEqual(labels["agro_input_dealer"], "Agrovet (retail shop)")
        self.assertEqual(labels["manufacturer"], "Supplier (manufacturer / producer / industry)")
        self.assertTrue(self.shop.is_agrovet and not self.shop.can_have_agronomists)
        self.assertTrue(self.company.can_have_agronomists and self.seedling.can_have_agronomists)

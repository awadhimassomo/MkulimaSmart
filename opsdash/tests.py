from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from assistant.models import Conversation, Message
from callcenter.models import Agronomist, Case, Heartbeat
from gova_pp.models import GovernmentOfficial
from kikapu_bridge.models import ReplyDelivery

User = get_user_model()


class OpsBase(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.admin = User.objects.create_superuser(password="pass12345", email="admin@mkulima.test")
        self.client = Client()
        self.client.force_login(self.admin)

    def conversation(self, phone="+255712345678", **fields):
        fields.setdefault("farmer_name", "Niko Simiyu")
        return Conversation.objects.create(phone_number=phone, **fields)

    def agronomist(self, email="asha@zamseed.test", **fields):
        user = User.objects.create_user(password="pass12345", email=email)
        fields.setdefault("full_name", "Asha Mwakyusa")
        return Agronomist.objects.create(user=user, **fields)

    def delivery(self, conversation, **fields):
        message = Message.objects.create(conversation=conversation, role="assistant", text="Reply text")
        return ReplyDelivery.objects.create(message=message, phone_number=conversation.phone_number, payload={"text": "Reply text", "source": "ai"}, **fields)


class AccessTests(OpsBase):
    PAGES = ["ops:overview", "ops:agronomists", "ops:chats", "ops:deliveries"]

    def test_every_page_opens_for_an_administrator(self):
        for name in self.PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_staff_and_officers_are_turned_away(self):
        staff = Client()
        staff.force_login(User.objects.create_user(password="pass12345", email="staff@gov.test", is_staff=True))
        for name in self.PAGES:
            self.assertEqual(staff.get(reverse(name)).status_code, 403, name)

    def test_signed_out_visitors_go_to_the_login(self):
        for name in self.PAGES:
            self.assertRedirects(Client().get(reverse(name)), reverse("gova_pp:login"), fetch_redirect_response=False)

    def test_only_an_administrator_can_act(self):
        agronomist = self.agronomist()
        delivery = self.delivery(self.conversation(), gave_up=True)
        outsider = Client()
        outsider.force_login(User.objects.create_user(password="pass12345", email="x@y.test", is_staff=True))
        outsider.post(reverse("ops:agronomist_toggle", args=[agronomist.pk]))
        outsider.post(reverse("ops:delivery_retry", args=["reply", delivery.pk]))
        self.assertTrue(Agronomist.objects.get().is_active)
        self.assertTrue(ReplyDelivery.objects.get().gave_up)


class OverviewTests(OpsBase):
    def test_a_quiet_platform_says_nothing_needs_attention(self):
        self.assertContains(self.client.get(reverse("ops:overview")), "Nothing needs attention")

    def test_pending_officers_are_flagged(self):
        user = User.objects.create_user(password="pass12345", email="o@x.go.tz")
        GovernmentOfficial.objects.create(user=user, full_name="O", institution="X")
        page = self.client.get(reverse("ops:overview"))
        self.assertContains(page, "1 government request(s) waiting for approval")
        self.assertContains(page, 'class="badge">1<')  # the navigation shows it too

    @override_settings(CALLCENTER_ENABLED=True)
    def test_a_stopped_worker_is_flagged_only_when_the_call_center_is_on(self):
        self.assertContains(self.client.get(reverse("ops:overview")), "worker is not running")
        Heartbeat.beat()
        self.assertNotContains(self.client.get(reverse("ops:overview")), "worker is not running")
        with override_settings(CALLCENTER_ENABLED=False):
            Heartbeat.objects.all().delete()
            self.assertNotContains(self.client.get(reverse("ops:overview")), "worker is not running")

    @override_settings(CALLCENTER_ENABLED=True, CALLCENTER_ACCEPT_SECONDS=120)
    def test_chats_that_waited_too_long_are_flagged(self):
        Heartbeat.beat()
        case = Case.objects.create(conversation=self.conversation())
        Case.objects.filter(pk=case.pk).update(waiting_since=timezone.now() - timedelta(minutes=10))
        self.assertContains(self.client.get(reverse("ops:overview")), "waited far longer than expected")

    def test_failed_and_stuck_messages_to_kikapu_are_flagged(self):
        conversation = self.conversation()
        self.delivery(conversation)
        self.assertContains(self.client.get(reverse("ops:overview")), "not yet delivered to Kikapu")
        self.delivery(conversation, gave_up=True)
        self.assertContains(self.client.get(reverse("ops:overview")), "failed for good")

    def test_experts_needed_are_flagged(self):
        self.conversation(needs_expert=True)
        self.assertContains(self.client.get(reverse("ops:overview")), "told to see an expert")


class AgronomistTests(OpsBase):
    def test_lists_everyone_with_their_workload(self):
        agronomist = self.agronomist(is_available=True, last_seen=timezone.now())
        case = Case.objects.create(conversation=self.conversation(), status=Case.OPEN, agronomist=agronomist)
        page = self.client.get(reverse("ops:agronomists"))
        self.assertContains(page, "Asha Mwakyusa")
        self.assertContains(page, "Online")
        self.assertContains(page, "1 chat open")
        self.assertEqual(case.agronomist, agronomist)

    def test_switching_access_off_returns_their_chats_to_the_queue(self):
        agronomist = self.agronomist(is_available=True, last_seen=timezone.now())
        case = Case.objects.create(conversation=self.conversation(), status=Case.OPEN, agronomist=agronomist)
        self.client.post(reverse("ops:agronomist_toggle", args=[agronomist.pk]))
        agronomist.refresh_from_db()
        case.refresh_from_db()
        self.assertFalse(agronomist.is_active or agronomist.is_available)
        self.assertEqual((case.status, case.agronomist), (Case.WAITING, None))
        self.client.post(reverse("ops:agronomist_toggle", args=[agronomist.pk]))
        self.assertTrue(Agronomist.objects.get().is_active)

    def test_an_empty_list_says_how_agronomists_join(self):
        self.assertContains(self.client.get(reverse("ops:agronomists")), "invite them")


class ChatTests(OpsBase):
    def setUp(self):
        super().setUp()
        self.niko = self.conversation(region="Mbeya")
        self.zawadi = self.conversation(phone="+255755000111", farmer_name="Zawadi", needs_expert=True)
        Message.objects.create(conversation=self.niko, role="farmer", text="Majani yanageuka njano")
        agronomist = self.agronomist()
        Message.objects.create(conversation=self.niko, role="agronomist", text="Weka mbolea ya CAN", payload={"name": "Asha Mwakyusa"})
        Case.objects.create(conversation=self.niko, status=Case.OPEN, agronomist=agronomist)

    def test_list_search_and_filters(self):
        url = reverse("ops:chats")
        page = self.client.get(url)
        self.assertContains(page, "Niko Simiyu")
        self.assertContains(page, "+255712345678")  # administrators see the whole number
        self.assertContains(page, "Zawadi")
        found = self.client.get(url, {"q": "zawadi"})
        self.assertContains(found, "Zawadi")
        self.assertNotContains(found, "Niko Simiyu")
        self.assertNotContains(self.client.get(url, {"q": "Mbeya"}), "Zawadi")
        experts = self.client.get(url, {"state": "expert"})
        self.assertContains(experts, "Zawadi")
        self.assertNotContains(experts, "Niko Simiyu")
        open_chats = self.client.get(url, {"state": "open"})
        self.assertContains(open_chats, "Niko Simiyu")
        self.assertNotContains(open_chats, "Zawadi")

    def test_a_chat_shows_the_transcript_and_who_handled_it(self):
        page = self.client.get(reverse("ops:chat", args=[self.niko.pk]))
        self.assertContains(page, "Majani yanageuka njano")
        self.assertContains(page, "Weka mbolea ya CAN")
        self.assertContains(page, "With an agronomist: Asha Mwakyusa")

    def test_the_chat_shows_whether_photos_may_be_used_for_training(self):
        url = reverse("ops:chat", args=[self.niko.pk])
        self.assertContains(self.client.get(url), "Not answered, so not allowed")
        Conversation.objects.filter(pk=self.niko.pk).update(training_consent=True)
        self.assertContains(self.client.get(url), "Allowed")
        Conversation.objects.filter(pk=self.niko.pk).update(training_consent=False)
        self.assertContains(self.client.get(url), "Declined")

    def test_an_unknown_chat_is_a_404(self):
        self.assertEqual(self.client.get(reverse("ops:chat", args=[9999])).status_code, 404)

    def test_the_list_is_paged(self):
        for i in range(30):
            self.conversation(phone=f"+2557000000{i:02d}", farmer_name=f"Farmer {i}")
        page = self.client.get(reverse("ops:chats"))
        self.assertContains(page, "Page 1 of 2")
        self.assertContains(self.client.get(reverse("ops:chats"), {"page": 2}), "Page 2 of 2")


class DeliveryTests(OpsBase):
    def test_lists_undelivered_messages_and_retries_a_failed_one(self):
        conversation = self.conversation()
        failed = self.delivery(conversation, gave_up=True, attempts=20, last_error="HTTP 503: down")
        delivered = self.delivery(conversation, delivered_at=timezone.now())
        page = self.client.get(reverse("ops:deliveries"))
        self.assertContains(page, "HTTP 503: down")
        self.assertContains(page, "Gave up")
        self.client.post(reverse("ops:delivery_retry", args=["reply", failed.pk]))
        failed.refresh_from_db()
        self.assertEqual((failed.gave_up, failed.attempts), (False, 0))
        self.assertIsNotNone(ReplyDelivery.objects.get(pk=delivered.pk).delivered_at)  # delivered ones are left alone

    def test_an_unknown_kind_does_nothing(self):
        self.assertRedirects(self.client.post(reverse("ops:delivery_retry", args=["bogus", 1])), reverse("ops:deliveries"))


class HeartbeatTests(OpsBase):
    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_the_worker_records_that_it_ran(self, _):
        self.assertIsNone(Heartbeat.age_seconds())
        call_command("run_callcenter")
        self.assertLess(Heartbeat.age_seconds(), 5)

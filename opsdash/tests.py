from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from assistant.models import Conversation, Message
from callcenter.models import Agronomist, Case, Heartbeat, Invite
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
        self.assertContains(self.client.get(reverse("ops:agronomists")), "Create an invite link above")


class InviteTests(OpsBase):
    def setUp(self):
        super().setUp()
        from operations.models import InputSeller

        owner = User.objects.create_user(password="pass12345", email="owner@zamseed.test", is_supplier=True)
        self.company = InputSeller.objects.create(
            user=owner, seller_name="Zamseed", business_name="Zamseed Tanzania", phone_number="0712000001",
            seller_type="manufacturer", location="Arusha", onboarding_completed=True,
        )

    def test_the_page_offers_every_active_company(self):
        self.assertContains(self.client.get(reverse("ops:agronomists")), "Zamseed Tanzania (Input Manufacturer / Distributor)")

    def test_an_administrator_creates_a_link_for_a_company(self):
        response = self.client.post(reverse("ops:invite_create"), {"company": self.company.pk, "name": "Neema"})
        self.assertRedirects(response, reverse("ops:agronomists"))
        invite = Invite.objects.get()
        self.assertEqual((invite.company, invite.name, invite.created_by), (self.company, "Neema", self.admin))
        page = self.client.get(reverse("ops:agronomists"))
        self.assertContains(page, reverse("callcenter:join", args=[invite.token]))
        self.assertContains(page, "Neema")

    def test_the_link_works_for_the_agronomist(self):
        self.client.post(reverse("ops:invite_create"), {"company": self.company.pk})
        invite = Invite.objects.get()
        response = Client().post(reverse("callcenter:join", args=[invite.token]), {
            "full_name": "Neema Joseph", "email": "neema@zamseed.test", "password": "Str0ng-pass-99", "password2": "Str0ng-pass-99",
        })
        self.assertRedirects(response, reverse("callcenter:console"), fetch_redirect_response=False)
        self.assertEqual(Agronomist.objects.get(user__email="neema@zamseed.test").company, self.company)

    def test_a_company_is_required(self):
        self.client.post(reverse("ops:invite_create"), {"company": "", "name": "Neema"})
        self.client.post(reverse("ops:invite_create"), {"company": 99999})
        self.assertFalse(Invite.objects.exists())

    def test_cancelling_a_link(self):
        invite = Invite.objects.create(company=self.company)
        self.client.post(reverse("ops:invite_revoke", args=[invite.pk]))
        self.assertFalse(Invite.objects.exists())

    def test_used_links_are_not_listed_and_cannot_be_cancelled(self):
        used = Invite.objects.create(company=self.company, name="Used one", used_at=timezone.now())
        self.assertNotContains(self.client.get(reverse("ops:agronomists")), "Used one")
        self.assertEqual(self.client.post(reverse("ops:invite_revoke", args=[used.pk])).status_code, 404)

    def test_only_administrators_can_create_links(self):
        staff = Client()
        staff.force_login(User.objects.create_user(password="pass12345", email="staff@gov.test", is_staff=True))
        self.assertEqual(staff.post(reverse("ops:invite_create"), {"company": self.company.pk}).status_code, 403)
        self.assertFalse(Invite.objects.exists())


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


class AccountsTests(OpsBase):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(
            password="old-pass-123", email="neema@zamseed.test", phone_number="+255712345678", first_name="Neema", last_name="Joseph",
        )

    def test_search_by_email_phone_or_name(self):
        url = reverse("ops:accounts")
        for term in ("neema@zamseed", "712345678", "Joseph"):
            self.assertContains(self.client.get(url, {"q": term}), "Neema Joseph", msg_prefix=term)
        self.assertContains(self.client.get(url, {"q": "nobody-like-this"}), "Nobody matches")
        self.assertNotContains(self.client.get(url), "Results")  # nothing is listed until you search

    def test_a_reset_link_is_created_and_shown_once(self):
        response = self.client.post(reverse("ops:account_reset_link", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)
        link = response.context["link"]
        self.assertIn("/reset/", link)
        self.assertContains(response, link)
        self.assertContains(response, "expires after 3 days")
        self.assertNotContains(self.client.get(reverse("ops:accounts"), {"q": "neema"}), "/reset/")  # not stored or listed

    def test_the_link_lets_the_person_choose_a_new_password(self):
        link = self.client.post(reverse("ops:account_reset_link", args=[self.person.pk])).context["link"]
        guest = Client()
        opened = guest.get(link, follow=True)
        self.assertEqual(opened.status_code, 200)
        form_url = opened.redirect_chain[-1][0]
        done = guest.post(form_url, {"new_password1": "Brand-new-pass-77", "new_password2": "Brand-new-pass-77"})
        self.assertEqual(done.status_code, 302)
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("Brand-new-pass-77"))
        self.assertFalse(self.person.check_password("old-pass-123"))

    def test_a_link_works_only_once(self):
        link = self.client.post(reverse("ops:account_reset_link", args=[self.person.pk])).context["link"]
        guest = Client()
        form_url = guest.get(link, follow=True).redirect_chain[-1][0]
        guest.post(form_url, {"new_password1": "Brand-new-pass-77", "new_password2": "Brand-new-pass-77"})
        second = Client().get(link, follow=True)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.context["validlink"])  # the used link no longer offers the password form
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("Brand-new-pass-77"))

    def test_the_accounts_page_marks_administrators_and_accounts_without_email(self):
        phone_only = User.objects.create_user(password="pass12345", phone_number="+255799000111")
        page = self.client.get(reverse("ops:accounts"), {"q": "admin@mkulima"})
        self.assertContains(page, "Administrator")
        page = self.client.get(reverse("ops:accounts"), {"q": "799000111"})
        self.assertContains(page, "no email")
        self.assertEqual(phone_only.email, None)

    def test_only_administrators(self):
        staff = Client()
        staff.force_login(User.objects.create_user(password="pass12345", email="staff@gov.test", is_staff=True))
        self.assertEqual(staff.get(reverse("ops:accounts")).status_code, 403)
        self.assertEqual(staff.post(reverse("ops:account_reset_link", args=[self.person.pk])).status_code, 403)
        self.assertEqual(Client().get(reverse("ops:accounts")).status_code, 302)

    def test_it_is_in_the_navigation(self):
        self.assertContains(self.client.get(reverse("ops:overview")), reverse("ops:accounts"))


class AccountEmailTests(OpsBase):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(password="old-pass-123", email="neema@zamseed.test", first_name="Neema")

    def send(self, user=None):
        return self.client.post(reverse("ops:account_reset_email", args=[(user or self.person).pk]), follow=True)

    def test_the_email_goes_to_the_person_with_a_working_link(self):
        from django.core import mail

        response = self.send()
        self.assertContains(response, "A reset email was sent to neema@zamseed.test")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["neema@zamseed.test"])
        self.assertIn("Reset your Mkulima Smart password", message.subject)
        self.assertIn("Weka upya nenosiri", message.subject)
        self.assertEqual(len(message.subject.splitlines()), 1)
        link = next(word for word in message.body.split() if "/reset/" in word)
        self.assertTrue(link.startswith("http"))
        guest = Client()
        form_url = guest.get(link.replace("http://testserver", ""), follow=True).redirect_chain[-1][0]
        guest.post(form_url, {"new_password1": "Brand-new-pass-77", "new_password2": "Brand-new-pass-77"})
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("Brand-new-pass-77"))

    def test_the_email_is_in_english_and_swahili(self):
        from django.core import mail

        self.send()
        self.assertIn("Someone asked to reset the password", mail.outbox[0].body)
        self.assertIn("Kuna mtu ameomba kuweka upya nenosiri", mail.outbox[0].body)

    def test_an_account_without_email_gets_a_helpful_message(self):
        from django.core import mail

        phone_only = User.objects.create_user(password="pass12345", phone_number="+255799000111")
        self.assertContains(self.send(phone_only), "has no email address")
        self.assertEqual(len(mail.outbox), 0)

    def test_a_mail_server_problem_is_reported_not_a_crash(self):
        with mock.patch("opsdash.views.send_mail", side_effect=OSError("connection refused")):
            response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be sent")

    def test_the_email_button_is_only_offered_when_there_is_an_address(self):
        User.objects.create_user(password="pass12345", phone_number="+255799000111", first_name="Phoneonly")
        page = self.client.get(reverse("ops:accounts"), {"q": "Phoneonly"})
        self.assertNotContains(page, "Email the link")
        self.assertContains(self.client.get(reverse("ops:accounts"), {"q": "neema"}), "Email the link")

    def test_only_administrators_can_send(self):
        from django.core import mail

        staff = Client()
        staff.force_login(User.objects.create_user(password="pass12345", email="staff@gov.test", is_staff=True))
        self.assertEqual(staff.post(reverse("ops:account_reset_email", args=[self.person.pk])).status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

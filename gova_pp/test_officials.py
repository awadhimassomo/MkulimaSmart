from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from . import officials
from .models import GovernmentInvite, GovernmentOfficial

User = get_user_model()
PASSWORD = "Str0ng-pass-99"


def signup_data(**overrides):
    data = {
        "full_name": "Neema Joseph", "job_title": "Extension officer", "institution": "Mbeya Rural District Council",
        "region": "Mbeya", "district": "Mbeya Rural", "reason": "I answer farmers questions for the council.",
        "email": "Neema@Council.go.tz", "phone": "", "password": PASSWORD, "password2": PASSWORD, "website": "",
    }
    data.update(overrides)
    return data


class OfficialTestBase(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.admin = User.objects.create_superuser(password="pass12345", email="admin@mkulima.test")
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)

    def request_access(self, **overrides):
        return Client().post(reverse("gova_pp:signup"), signup_data(**overrides))

    def official(self, email="neema@council.go.tz"):
        return GovernmentOfficial.objects.get(user__email=email)

    def decide(self, official, action, **data):
        return self.admin_client.post(reverse("gova_pp:official_decide", args=[official.pk, action]), data)


class SignupWithApprovalTests(OfficialTestBase):
    def test_a_request_creates_a_pending_account_with_no_access(self):
        response = self.request_access()
        self.assertContains(response, "Request received")
        official = self.official()
        self.assertEqual(official.status, GovernmentOfficial.PENDING)
        self.assertFalse(official.user.is_staff)
        self.assertEqual(official.institution, "Mbeya Rural District Council")

    def test_a_pending_officer_cannot_sign_in_and_is_told_why(self):
        self.request_access()
        client = Client()
        response = client.post(reverse("gova_pp:login"), {"email": "neema@council.go.tz", "password": PASSWORD})
        self.assertContains(response, "waiting for approval")
        self.assertNotIn("_auth_user_id", client.session)

    def test_approval_grants_the_dashboard(self):
        self.request_access()
        official = self.official()
        response = self.decide(official, "approve", note="Confirmed with the council")
        self.assertRedirects(response, reverse("gova_pp:officials"))
        official.refresh_from_db()
        self.assertEqual((official.status, official.decided_by, official.decision_note), ("approved", self.admin, "Confirmed with the council"))
        self.assertTrue(official.user.is_staff)
        login = Client().post(reverse("gova_pp:login"), {"email": "neema@council.go.tz", "password": PASSWORD})
        self.assertRedirects(login, reverse("gova_pp:dashboard"), fetch_redirect_response=False)

    def test_turning_down_keeps_them_out_and_says_so(self):
        self.request_access()
        official = self.official()
        self.decide(official, "reject", note="Not an officer")
        official.refresh_from_db()
        self.assertFalse(official.user.is_staff)
        response = Client().post(reverse("gova_pp:login"), {"email": "neema@council.go.tz", "password": PASSWORD})
        self.assertContains(response, "was not approved")

    def test_suspending_removes_access_and_reinstating_restores_it(self):
        self.request_access()
        official = self.official()
        self.decide(official, "approve")
        self.decide(official, "suspend")
        official.user.refresh_from_db()
        self.assertFalse(official.user.is_staff)
        self.assertContains(Client().post(reverse("gova_pp:login"), {"email": "neema@council.go.tz", "password": PASSWORD}), "suspended")
        self.decide(official, "reinstate")
        official.user.refresh_from_db()
        self.assertTrue(official.user.is_staff)

    def test_an_account_that_was_already_staff_keeps_its_access_when_suspended(self):
        staff = User.objects.create_user(password="pass12345", email="old@gov.test", is_staff=True)
        official = GovernmentOfficial.objects.create(user=staff, full_name="Old Hand", institution="Ministry")
        officials.approve(official, self.admin)
        officials.suspend(official, self.admin)
        staff.refresh_from_db()
        self.assertTrue(staff.is_staff)  # we did not grant it, so we do not take it

    def test_a_superuser_is_never_demoted(self):
        official = GovernmentOfficial.objects.create(user=self.admin, full_name="Boss", institution="Ministry", staff_granted=True)
        officials.suspend(official, self.admin)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)

    def test_form_checks(self):
        self.request_access()
        self.assertContains(self.request_access(), "already exists")  # same email again
        self.assertContains(self.request_access(email="b@x.go.tz", password2="other"), "do not match")
        self.assertContains(self.request_access(email="b@x.go.tz", password="12345678", password2="12345678"), "too common")
        self.assertContains(self.request_access(email="b@x.go.tz", reason=""), "required")
        self.assertEqual(GovernmentOfficial.objects.count(), 1)

    def test_a_phone_number_already_in_use_is_refused(self):
        User.objects.create_user(phone_number="+255712000111", password="pass12345", email="someone@x.test")
        self.assertContains(self.request_access(email="c@x.go.tz", phone="+255 712 000 111"), "another account")

    def test_the_honeypot_catches_bots_without_creating_anything(self):
        response = self.request_access(website="http://spam.example")
        self.assertContains(response, "Request received")
        self.assertFalse(GovernmentOfficial.objects.exists())

    def test_requests_from_one_connection_are_limited(self):
        for i in range(5):
            self.request_access(email=f"o{i}@x.go.tz")
        blocked = self.request_access(email="o9@x.go.tz")
        self.assertContains(blocked, "Too many requests")
        self.assertEqual(GovernmentOfficial.objects.count(), 5)


class InviteTests(OfficialTestBase):
    def make_invite(self, **fields):
        return GovernmentInvite.objects.create(created_by=self.admin, expires_at=timezone.now() + timedelta(days=7), **fields)

    def test_administrator_creates_an_invite_and_sees_its_link(self):
        self.admin_client.post(reverse("gova_pp:official_invite"), {"name": "Neema", "institution": "Mbeya DC", "region": "Mbeya"})
        invite = GovernmentInvite.objects.get()
        self.assertEqual((invite.name, invite.institution, invite.created_by), ("Neema", "Mbeya DC", self.admin))
        page = self.admin_client.get(reverse("gova_pp:officials"))
        self.assertContains(page, reverse("gova_pp:join", args=[invite.token]))

    def test_signing_up_with_an_invite_needs_no_further_approval(self):
        invite = self.make_invite(name="Neema", institution="Mbeya DC")
        guest = Client()
        self.assertContains(guest.get(reverse("gova_pp:join", args=[invite.token])), "Mbeya DC")
        data = signup_data()
        data.pop("reason")
        response = guest.post(reverse("gova_pp:join", args=[invite.token]), data)
        self.assertRedirects(response, reverse("gova_pp:dashboard"), fetch_redirect_response=False)
        official = self.official()
        self.assertEqual((official.status, official.via, official.decided_by), ("approved", "invite", self.admin))
        self.assertTrue(official.user.is_staff)
        self.assertEqual(guest.get(reverse("gova_pp:dashboard")).status_code, 200)  # already signed in
        invite.refresh_from_db()
        self.assertEqual(invite.official, official)

    def test_an_invite_works_only_once(self):
        invite = self.make_invite()
        data = signup_data()
        data.pop("reason")
        Client().post(reverse("gova_pp:join", args=[invite.token]), data)
        again = Client().post(reverse("gova_pp:join", args=[invite.token]), {**data, "email": "other@x.go.tz"})
        self.assertEqual(again.status_code, 410)
        self.assertFalse(User.objects.filter(email="other@x.go.tz").exists())

    def test_expired_cancelled_and_unknown_links_do_not_work(self):
        expired = self.make_invite()
        GovernmentInvite.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(Client().get(reverse("gova_pp:join", args=[expired.token])).status_code, 410)
        cancelled = self.make_invite()
        self.admin_client.post(reverse("gova_pp:official_invite_revoke", args=[cancelled.pk]))
        self.assertEqual(Client().get(reverse("gova_pp:join", args=[cancelled.token])).status_code, 410)
        self.assertEqual(Client().get(reverse("gova_pp:join", args=["nope"])).status_code, 410)


class AdministratorOnlyTests(OfficialTestBase):
    def test_only_a_superuser_sees_the_page_or_decides(self):
        self.request_access()
        official = self.official()
        staff = Client()
        staff.force_login(User.objects.create_user(password="pass12345", email="staff@gov.test", is_staff=True))
        self.assertEqual(staff.get(reverse("gova_pp:officials")).status_code, 403)
        self.assertEqual(staff.post(reverse("gova_pp:official_decide", args=[official.pk, "approve"])).status_code, 403)
        self.assertEqual(staff.post(reverse("gova_pp:official_invite")).status_code, 403)
        official.refresh_from_db()
        self.assertEqual(official.status, GovernmentOfficial.PENDING)

    def test_signed_out_visitors_go_to_the_login(self):
        self.assertRedirects(Client().get(reverse("gova_pp:officials")), reverse("gova_pp:login"), fetch_redirect_response=False)

    def test_the_page_lists_requests_with_their_reasons(self):
        self.request_access()
        page = self.admin_client.get(reverse("gova_pp:officials"))
        self.assertContains(page, "Neema Joseph")
        self.assertContains(page, "I answer farmers")
        self.assertContains(page, "Mbeya Rural District Council")

    def test_an_unknown_action_does_nothing(self):
        self.request_access()
        official = self.official()
        self.decide(official, "delete")
        official.refresh_from_db()
        self.assertEqual(official.status, GovernmentOfficial.PENDING)

    def test_the_sign_in_page_links_to_the_request_form(self):
        self.assertContains(Client().get(reverse("gova_pp:login")), reverse("gova_pp:signup"))

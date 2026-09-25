from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from .models import Discussion, Reply

User = get_user_model()


def make_user(phone):
    return User.objects.create_user(phone_number=phone, password="pass12345", is_farmer=True)


class LocalizedTestCase(TestCase):
    """
    settings.LANGUAGE_CODE is "en-us", which is not in LANGUAGES, so reverse() would build
    /en-us/ URLs (404) until some request activates a supported language. Activate one up front.
    """

    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)


class DiscussionModelTests(LocalizedTestCase):
    def setUp(self):
        super().setUp()
        self.farmer = make_user("0700000001")
        self.discussion = Discussion.objects.create(
            author=self.farmer, crop="Maize", seed_variety="Zamseed 606",
            title="Zamseed 606 on 1 acre", body="Planted 3 packets, harvested 145 debe.",
        )

    def test_reply_count_increments_and_decrements_via_signal(self):
        self.assertEqual(self.discussion.reply_count, 0)
        r1 = Reply.objects.create(discussion=self.discussion, author=self.farmer, body="Nice yield!")
        Reply.objects.create(discussion=self.discussion, author=self.farmer, body="Which region?")
        self.discussion.refresh_from_db()
        self.assertEqual(self.discussion.reply_count, 2)

        r1.delete()
        self.discussion.refresh_from_db()
        self.assertEqual(self.discussion.reply_count, 1)

    def test_reply_count_never_goes_negative(self):
        # A discussion with no replies still has reply_count == 0; the update guard
        # (reply_count__gt=0) must not push it negative if a delete signal ever double-fires.
        Discussion.objects.filter(pk=self.discussion.pk).update(reply_count=0)
        from community.signals import _decrement_reply_count
        _decrement_reply_count(sender=Reply, instance=self.discussion.replies.model(discussion_id=self.discussion.pk))
        self.discussion.refresh_from_db()
        self.assertEqual(self.discussion.reply_count, 0)


class DiscussionListViewTests(LocalizedTestCase):
    def setUp(self):
        super().setUp()
        self.farmer = make_user("0700000002")
        Discussion.objects.create(author=self.farmer, crop="Maize", title="Maize season 1", body="Good yield with Zamseed 606")
        Discussion.objects.create(author=self.farmer, crop="Beans", title="Beans question", body="Best variety for clay soil?", kind="question")
        Discussion.objects.create(author=self.farmer, crop="Maize", title="Hidden one", body="spam", is_active=False)

    def test_list_is_public_and_hides_inactive(self):
        response = self.client.get(reverse("community:discussion_list"))
        self.assertEqual(response.status_code, 200)
        titles = [d.title for d in response.context["discussions"]]
        self.assertIn("Maize season 1", titles)
        self.assertIn("Beans question", titles)
        self.assertNotIn("Hidden one", titles)

    def test_filter_by_crop(self):
        response = self.client.get(reverse("community:discussion_list"), {"crop": "Beans"})
        titles = [d.title for d in response.context["discussions"]]
        self.assertEqual(titles, ["Beans question"])

    def test_filter_by_kind(self):
        response = self.client.get(reverse("community:discussion_list"), {"kind": "question"})
        titles = [d.title for d in response.context["discussions"]]
        self.assertEqual(titles, ["Beans question"])

    def test_search_matches_body_and_variety(self):
        response = self.client.get(reverse("community:discussion_list"), {"q": "Zamseed 606"})
        titles = [d.title for d in response.context["discussions"]]
        self.assertEqual(titles, ["Maize season 1"])

    def test_top_crops_counts_active_only(self):
        response = self.client.get(reverse("community:discussion_list"))
        crops = {row["crop"]: row["total"] for row in response.context["top_crops"]}
        self.assertEqual(crops.get("Maize"), 1)  # the inactive Maize post is excluded


class DiscussionCreateViewTests(LocalizedTestCase):
    def setUp(self):
        super().setUp()
        self.farmer = make_user("0700000003")

    def test_requires_login(self):
        response = self.client.get(reverse("community:discussion_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_logged_in_farmer_can_post(self):
        self.client.force_login(self.farmer)
        response = self.client.post(reverse("community:discussion_create"), {
            "kind": "experience", "crop": "Maize", "seed_variety": "Zamseed 606",
            "title": "1 acre, 3 packets, 145 debe", "body": "Long body text about the season.",
            "region": "Simiyu",
        })
        discussion = Discussion.objects.get(title="1 acre, 3 packets, 145 debe")
        self.assertRedirects(response, reverse("community:discussion_detail", kwargs={"pk": discussion.pk}))
        self.assertEqual(discussion.author, self.farmer)

    def test_missing_required_fields_reshows_form(self):
        self.client.force_login(self.farmer)
        response = self.client.post(reverse("community:discussion_create"), {"kind": "experience"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Discussion.objects.exists())
        self.assertTrue(response.context["form"].errors)


class DiscussionDetailAndReplyTests(LocalizedTestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("0700000004")
        self.replier = make_user("0700000005")
        self.discussion = Discussion.objects.create(
            author=self.author, crop="Maize", title="Season report", body="Details here.",
        )

    def test_detail_visible_to_anonymous(self):
        response = self.client.get(self.discussion.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Season report")

    def test_hidden_discussion_returns_404(self):
        self.discussion.is_active = False
        self.discussion.save()
        response = self.client.get(self.discussion.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_anonymous_reply_redirects_to_login_prompt(self):
        response = self.client.post(self.discussion.get_absolute_url(), {"body": "Nice!"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Reply.objects.exists())

    def test_logged_in_user_can_reply(self):
        self.client.force_login(self.replier)
        response = self.client.post(self.discussion.get_absolute_url(), {"body": "How many bags of fertilizer did you use?"})
        self.assertRedirects(response, self.discussion.get_absolute_url())
        reply = Reply.objects.get()
        self.assertEqual(reply.author, self.replier)
        self.assertEqual(reply.discussion, self.discussion)

    def test_empty_reply_rejected(self):
        self.client.force_login(self.replier)
        response = self.client.post(self.discussion.get_absolute_url(), {"body": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Reply.objects.exists())


class DiscussionReportViewTests(LocalizedTestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("0700000006")
        self.reporter = make_user("0700000007")
        self.discussion = Discussion.objects.create(author=self.author, crop="Maize", title="x", body="y")

    def test_requires_login(self):
        response = self.client.post(reverse("community:discussion_report", kwargs={"pk": self.discussion.pk}))
        self.assertEqual(response.status_code, 302)

    def test_get_not_allowed(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("community:discussion_report", kwargs={"pk": self.discussion.pk}))
        self.assertEqual(response.status_code, 405)

    def test_logged_in_user_can_report(self):
        self.client.force_login(self.reporter)
        response = self.client.post(reverse("community:discussion_report", kwargs={"pk": self.discussion.pk}))
        self.assertRedirects(response, self.discussion.get_absolute_url())


class DiscussionsForNamesTests(TestCase):
    def setUp(self):
        self.farmer = make_user("0700000010")
        self.maize = Discussion.objects.create(
            author=self.farmer, crop="Maize", seed_variety="Zamseed 606",
            title="Zamseed 606 on 1 acre", body="3 packets, 145 debe harvest.",
        )
        self.beans = Discussion.objects.create(author=self.farmer, crop="Beans", title="Beans season", body="x")
        self.hidden = Discussion.objects.create(
            author=self.farmer, crop="Maize", title="Hidden", body="spam", is_active=False,
        )

    def test_matches_product_name_containing_crop(self):
        from community.utils import discussions_for_names
        results = list(discussions_for_names("Hybrid Maize Seed H614"))
        self.assertIn(self.maize, results)
        self.assertNotIn(self.beans, results)

    def test_matches_seed_variety(self):
        from community.utils import discussions_for_names
        results = list(discussions_for_names("Zamseed 606 (2kg packet)"))
        self.assertIn(self.maize, results)

    def test_excludes_inactive(self):
        from community.utils import discussions_for_names
        self.assertNotIn(self.hidden, list(discussions_for_names("Maize")))

    def test_no_names_returns_empty(self):
        from community.utils import discussions_for_names
        self.assertEqual(list(discussions_for_names("", None)), [])

    def test_short_words_are_not_used_for_exact_matching(self):
        # "of" and "on" (<=2 chars) shouldn't cause unrelated crop-name matches.
        from community.utils import discussions_for_names
        results = list(discussions_for_names("Bag of NPK on sale"))
        self.assertNotIn(self.maize, results)
        self.assertNotIn(self.beans, results)

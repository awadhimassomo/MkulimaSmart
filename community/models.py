"""
Farmer Talk: a public discussion board where farmers share what happened with a
crop or seed variety on their own farm ("planted 3 packets on 1 acre, harvested
145 debe"), ask for advice, and reply to each other — instead of that knowledge
staying scattered across private WhatsApp groups.

Read access is public. Posting and replying need a login.
"""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Discussion(models.Model):
    KIND_CHOICES = [
        ("experience", _("Farming experience")),
        ("question", _("Question")),
        ("advice", _("Tip / advice")),
    ]

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_discussions")
    kind = models.CharField(_("Type"), max_length=20, choices=KIND_CHOICES, default="experience")
    crop = models.CharField(_("Crop"), max_length=100, help_text=_("e.g. Maize, Beans, Tomato"))
    seed_variety = models.CharField(_("Seed / variety"), max_length=120, blank=True, help_text=_("e.g. Zamseed 606, H614"))
    title = models.CharField(_("Title"), max_length=200)
    body = models.TextField(_("Details"))
    region = models.CharField(_("Region"), max_length=60, blank=True)
    photo = models.ImageField(_("Photo"), upload_to="community/discussions/", blank=True, null=True)
    reply_count = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True, help_text=_("Hide from listings without deleting (e.g. spam)."))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["crop"]), models.Index(fields=["-created_at"])]
        verbose_name = _("Discussion")
        verbose_name_plural = _("Discussions")

    def __str__(self):
        return f"{self.crop}: {self.title}"

    def get_absolute_url(self):
        return reverse("community:discussion_detail", kwargs={"pk": self.pk})


class Reply(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_replies")
    body = models.TextField(_("Reply"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Reply")
        verbose_name_plural = _("Replies")

    def __str__(self):
        return f"Reply by {self.author} on {self.discussion_id}"

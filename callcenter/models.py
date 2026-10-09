"""
Call center for farmers. Seed and input companies (and their shops) invite their agronomists; when a
farmer writes in on WhatsApp, the agronomists who are online are offered the chat and the first to
accept answers it. If nobody accepts in time (or nobody is online), the AI assistant answers instead.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def setting(name, default):
    return getattr(settings, name, default)


class Agronomist(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agronomist_profile")
    company = models.ForeignKey(
        "operations.InputSeller", on_delete=models.SET_NULL, blank=True, null=True, related_name="agronomists",
        help_text="The input company or shop this agronomist works for.",
    )
    full_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, help_text="Untick to remove their access.")
    is_available = models.BooleanField(default=False, help_text="They switched themselves on to receive farmers.")
    last_seen = models.DateTimeField(blank=True, null=True, help_text="Last time their console was open.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.company_name})" if self.company_name else self.full_name

    @property
    def company_name(self):
        if not self.company:
            return ""
        return self.company.business_name or self.company.seller_name

    @property
    def is_online(self):
        """Switched on and with the console open in the last minute, so a closed laptop is not offered chats."""
        if not (self.is_active and self.is_available and self.last_seen):
            return False
        return timezone.now() - self.last_seen <= timedelta(seconds=setting("CALLCENTER_ONLINE_SECONDS", 60))

    @classmethod
    def online(cls):
        since = timezone.now() - timedelta(seconds=setting("CALLCENTER_ONLINE_SECONDS", 60))
        return cls.objects.filter(is_active=True, is_available=True, last_seen__gte=since)

    def touch(self):
        Agronomist.objects.filter(pk=self.pk).update(last_seen=timezone.now())


def new_token():
    return secrets.token_urlsafe(24)


class Invite(models.Model):
    """A one-time link a company sends to an agronomist so they can create their login."""

    company = models.ForeignKey("operations.InputSeller", on_delete=models.CASCADE, related_name="agronomist_invites")
    token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    name = models.CharField(max_length=120, blank=True, help_text="Who the link is for (optional).")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    agronomist = models.OneToOneField(Agronomist, on_delete=models.SET_NULL, blank=True, null=True, related_name="invite")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite for {self.name or 'agronomist'} at {self.company}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=setting("CALLCENTER_INVITE_DAYS", 7))
        super().save(*args, **kwargs)

    @property
    def usable(self):
        return self.used_at is None and self.expires_at > timezone.now()

    @property
    def state(self):
        if self.used_at:
            return "used"
        return "active" if self.expires_at > timezone.now() else "expired"


class Case(models.Model):
    """One farmer waiting for, or talking to, an agronomist (or handed to the AI)."""

    WAITING, OPEN, AI, CLOSED = "waiting", "open", "ai", "closed"
    STATUS_CHOICES = [
        (WAITING, "Waiting for an agronomist"),
        (OPEN, "With an agronomist"),
        (AI, "Answered by the AI"),
        (CLOSED, "Closed"),
    ]
    ACTIVE = (WAITING, OPEN, AI)

    conversation = models.ForeignKey("assistant.Conversation", on_delete=models.CASCADE, related_name="cases")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=WAITING, db_index=True)
    agronomist = models.ForeignKey(Agronomist, on_delete=models.SET_NULL, blank=True, null=True, related_name="cases")
    created_at = models.DateTimeField(auto_now_add=True)
    waiting_since = models.DateTimeField(default=timezone.now, help_text="When the farmer started waiting for someone to accept.")
    accepted_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    answered_by_ai = models.BooleanField(default=False, help_text="The AI answered at least once because no agronomist took it.")

    class Meta:
        ordering = ["-last_activity_at"]

    def __str__(self):
        return f"Case {self.pk}: {self.conversation} ({self.status})"

    @property
    def is_active(self):
        return self.status in self.ACTIVE

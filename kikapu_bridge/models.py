import hashlib
import secrets

from django.db import models
from django.utils import timezone


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PartnerToken(models.Model):
    """
    A long-lived API key issued to a partner (Kikapu) for calling /api/kikapu-bridge/.
    Only a SHA-256 hash is stored; the raw token is shown once when it is issued.
    """

    name = models.CharField(max_length=100, help_text="Who holds this key, e.g. Kikapu production.")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    token_prefix = models.CharField(max_length=8, editable=False, help_text="First characters, to recognise the key.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.token_prefix}…)"

    @classmethod
    def issue(cls, name):
        """Create a key and return (instance, raw_token). The raw token is not stored."""
        raw = "msk_" + secrets.token_urlsafe(32)
        token = cls.objects.create(name=name, token_hash=hash_token(raw), token_prefix=raw[:8])
        return token, raw

    def mark_used(self):
        # Avoid a database write on every request: at most once a minute.
        now = timezone.now()
        if not self.last_used_at or (now - self.last_used_at).total_seconds() > 60:
            PartnerToken.objects.filter(pk=self.pk).update(last_used_at=now)


class WebhookDelivery(models.Model):
    """Outbox of order status updates for Kikapu, retried until delivered."""

    MAX_ATTEMPTS = 20

    order = models.ForeignKey("inputs.FarmerOrder", on_delete=models.CASCADE, related_name="kikapu_webhooks")
    status = models.CharField(max_length=20)
    payload = models.JSONField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_response_code = models.PositiveSmallIntegerField(blank=True, null=True)
    last_error = models.CharField(max_length=255, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(blank=True, null=True)
    gave_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name_plural = "webhook deliveries"

    def __str__(self):
        return f"{self.order} → {self.status}"

    @property
    def state(self):
        if self.delivered_at:
            return "delivered"
        return "failed" if self.gave_up else "pending"

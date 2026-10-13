"""
Our own SMS gateway. An Android phone with a SIM (running our app) is the "modem": it uploads every SMS it receives
and sends the replies we put in the outbox. See docs/integrations/sms-gateway-device-api.md for the phone's side.
"""
import hashlib
import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

ONLINE_WINDOW = timedelta(minutes=3)


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Device(models.Model):
    """One gateway phone. It authenticates with a token (only the hash is stored) and is told its settings on every heartbeat."""

    name = models.CharField(max_length=100, help_text="For example: office phone 1.")
    project = models.CharField(
        max_length=40, default="mkulima",
        help_text="Which service this phone belongs to; decides how messages are understood (mkulima now, schools later).",
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    token_prefix = models.CharField(max_length=8, editable=False)
    is_active = models.BooleanField(default=True, help_text="Untick to revoke: the phone is refused from then on.")
    created_at = models.DateTimeField(auto_now_add=True)

    # what the phone last told us
    last_seen = models.DateTimeField(blank=True, null=True)
    app_version = models.CharField(max_length=20, blank=True)
    battery_percent = models.PositiveSmallIntegerField(blank=True, null=True)
    charging = models.BooleanField(blank=True, null=True)
    network = models.CharField(max_length=10, blank=True)
    signal = models.PositiveSmallIntegerField(blank=True, null=True)
    sim_operator = models.CharField(max_length=60, blank=True)
    sim_slot = models.PositiveSmallIntegerField(blank=True, null=True)
    sent_today = models.PositiveIntegerField(default=0)
    last_heartbeat = models.JSONField(default=dict, blank=True)

    # settings we control (returned on every heartbeat)
    paused = models.BooleanField(default=False, help_text="The phone keeps receiving but sends nothing.")
    heartbeat_seconds = models.PositiveSmallIntegerField(default=60)
    poll_interval_seconds = models.PositiveSmallIntegerField(default=5)
    idle_poll_interval_seconds = models.PositiveSmallIntegerField(default=10)
    send_interval_seconds = models.PositiveSmallIntegerField(default=4, help_text="Minimum gap between two SMS (operators block fast senders).")
    daily_send_limit = models.PositiveIntegerField(default=500)
    upload_batch_size = models.PositiveSmallIntegerField(default=20)
    allowed_senders = models.JSONField(blank=True, null=True, help_text="Empty means every sender; otherwise a list of numbers.")
    min_app_version = models.CharField(max_length=20, default="1.0.0")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.token_prefix}...)"

    @classmethod
    def issue(cls, name, project="mkulima"):
        """Create a device and return (device, raw_token). The raw token is not stored and cannot be shown again."""
        raw = "sgw_" + secrets.token_urlsafe(32)
        device = cls.objects.create(name=name, project=project, token_hash=hash_token(raw), token_prefix=raw[:8])
        return device, raw

    def touch(self):
        """Note that the phone just called us (at most one write every 20 seconds)."""
        now = timezone.now()
        if not self.last_seen or (now - self.last_seen).total_seconds() > 20:
            Device.objects.filter(pk=self.pk).update(last_seen=now)
            self.last_seen = now

    @property
    def is_online(self):
        return bool(self.is_active and self.last_seen and timezone.now() - self.last_seen <= ONLINE_WINDOW)

    def config(self):
        return {
            "heartbeat_seconds": self.heartbeat_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "idle_poll_interval_seconds": self.idle_poll_interval_seconds,
            "send_interval_seconds": self.send_interval_seconds,
            "daily_send_limit": self.daily_send_limit,
            "upload_batch_size": self.upload_batch_size,
            "paused": self.paused,
            "allowed_senders": self.allowed_senders or None,
            "min_app_version": self.min_app_version,
        }


class Contact(models.Model):
    """What we remember about one phone number that texts us: its language, and whether it asked us to stop."""

    phone = models.CharField(max_length=20, unique=True)
    language = models.CharField(max_length=5, default="sw")
    opted_out = models.BooleanField(default=False)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.phone


class InboundSms(models.Model):
    RECEIVED, PENDING, PROCESSED, IGNORED = "received", "pending", "processed", "ignored"
    STATUS_CHOICES = [(RECEIVED, "Received"), (PENDING, "Waiting to be answered"), (PROCESSED, "Answered"), (IGNORED, "Ignored")]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="inbox")
    client_id = models.CharField(max_length=64, help_text="Made by the phone when the SMS arrived; makes uploads safe to repeat.")
    sender = models.CharField(max_length=20)
    body = models.TextField()
    sent_at = models.DateTimeField(blank=True, null=True, help_text="The time the network stamped on the SMS.")
    received_at = models.DateTimeField(blank=True, null=True)
    sim_slot = models.PositiveSmallIntegerField(blank=True, null=True)
    parts = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=RECEIVED, db_index=True)
    handler = models.CharField(max_length=30, blank=True)
    note = models.CharField(max_length=200, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["device", "client_id"], name="unique_sms_client_id")]

    def __str__(self):
        return f"{self.sender}: {self.body[:30]}"


class OutboundSms(models.Model):
    QUEUED, LEASED, SENT, DELIVERED, FAILED, EXPIRED = "queued", "leased", "sent", "delivered", "failed", "expired"
    STATUS_CHOICES = [
        (QUEUED, "Waiting for the phone"), (LEASED, "Handed to the phone"), (SENT, "Sent"),
        (DELIVERED, "Delivered"), (FAILED, "Failed"), (EXPIRED, "Expired"),
    ]
    MAX_ATTEMPTS = 5

    device = models.ForeignKey(Device, on_delete=models.SET_NULL, blank=True, null=True, related_name="outbox")
    to = models.CharField(max_length=20)
    body = models.TextField()
    encoding = models.CharField(max_length=8, default="gsm7")
    parts = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=QUEUED, db_index=True)
    priority = models.SmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, help_text="Not offered to the phone before this time (retry delay).")
    lease_expires_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField()
    last_error = models.CharField(max_length=60, blank=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    in_reply_to = models.ForeignKey(InboundSms, on_delete=models.SET_NULL, blank=True, null=True, related_name="replies")
    handler = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"to {self.to}: {self.body[:30]}"

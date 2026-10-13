"""
The queue of SMS waiting to be sent by the phone.

queued -> leased (handed to the phone for a while) -> sent -> delivered, or failed / expired.
A failed message the phone says is worth retrying goes back to queued after a delay, up to MAX_ATTEMPTS times.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import text
from .models import Contact, OutboundSms

LEASE_SECONDS = 120
TTL = timedelta(hours=24)
RETRY_DELAY_SECONDS = 60


def send_sms(to, body, *, in_reply_to=None, handler="", priority=0, device=None, force=False, ttl=TTL):
    """
    Queue an SMS. Returns the OutboundSms, or None when it was not queued: a number we cannot text, an empty message,
    or someone who asked us to stop (unless `force`, used for the reply to STOP itself).
    """
    number = text.e164(to)
    body = text.shorten(body or "")
    if not number or not body:
        return None
    if not force and Contact.objects.filter(phone=number, opted_out=True).exists():
        return None
    encoding, _, parts = text.analyze(body)
    return OutboundSms.objects.create(
        to=number, body=body, encoding=encoding, parts=parts, in_reply_to=in_reply_to, handler=handler, priority=priority,
        device=device, expires_at=timezone.now() + ttl,
    )


def expire_old(now=None):
    """Messages that waited too long are given up on."""
    now = now or timezone.now()
    return OutboundSms.objects.filter(status__in=[OutboundSms.QUEUED, OutboundSms.LEASED], expires_at__lt=now).update(
        status=OutboundSms.EXPIRED, last_error="expired",
    )


def requeue_expired_leases(now=None):
    """A message handed to the phone that was never reported on goes back in the queue."""
    now = now or timezone.now()
    return OutboundSms.objects.filter(status=OutboundSms.LEASED, lease_expires_at__lt=now).update(
        status=OutboundSms.QUEUED, available_at=now,
    )


def lease(device, limit=10, now=None):
    """Hand the phone up to `limit` messages, oldest first (higher priority first), and mark them leased to it."""
    now = now or timezone.now()
    expire_old(now)
    requeue_expired_leases(now)
    candidates = list(
        OutboundSms.objects.filter(status=OutboundSms.QUEUED, available_at__lte=now)
        .filter(device__isnull=True)
        .order_by("-priority", "id")[:limit]
    ) + list(
        OutboundSms.objects.filter(status=OutboundSms.QUEUED, available_at__lte=now, device=device)
        .order_by("-priority", "id")[:limit]
    )
    candidates.sort(key=lambda sms: (-sms.priority, sms.pk))
    leased = []
    for sms in candidates[:limit]:
        with transaction.atomic():
            taken = OutboundSms.objects.filter(pk=sms.pk, status=OutboundSms.QUEUED).update(
                status=OutboundSms.LEASED, device=device, attempts=sms.attempts + 1,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
            )
        if taken:
            sms.refresh_from_db()
            leased.append(sms)
    return leased


def apply_status(sms, status, *, error="", retryable=False, at=None):
    """
    Record what the phone says happened to a message. Safe to repeat. A message already sent or delivered is not
    moved backwards, and a failure that is worth retrying goes back to the queue after a delay.
    """
    at = at or timezone.now()
    if status == "delivered":
        OutboundSms.objects.filter(pk=sms.pk).update(
            status=OutboundSms.DELIVERED, delivered_at=at, sent_at=sms.sent_at or at, last_error="", lease_expires_at=None,
        )
    elif status == "sent":
        if sms.status != OutboundSms.DELIVERED:
            OutboundSms.objects.filter(pk=sms.pk).update(status=OutboundSms.SENT, sent_at=at, last_error="", lease_expires_at=None)
    elif status == "failed":
        if sms.status in (OutboundSms.SENT, OutboundSms.DELIVERED):
            return  # it did go; a late failure report does not undo that
        if retryable and sms.attempts < OutboundSms.MAX_ATTEMPTS and error != "expired":
            OutboundSms.objects.filter(pk=sms.pk).update(
                status=OutboundSms.QUEUED, last_error=error[:60], lease_expires_at=None,
                available_at=timezone.now() + timedelta(seconds=RETRY_DELAY_SECONDS * max(1, sms.attempts)),
            )
        else:
            OutboundSms.objects.filter(pk=sms.pk).update(
                status=OutboundSms.EXPIRED if error == "expired" else OutboundSms.FAILED, last_error=error[:60], lease_expires_at=None,
            )


def requeue(sms):
    """Staff pressed "try again" on a failed or expired message."""
    OutboundSms.objects.filter(pk=sms.pk).update(
        status=OutboundSms.QUEUED, attempts=0, last_error="", available_at=timezone.now(),
        expires_at=timezone.now() + TTL, lease_expires_at=None,
    )

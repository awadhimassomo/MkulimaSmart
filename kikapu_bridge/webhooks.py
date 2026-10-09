"""
Order status webhook to Kikapu (spec §7).

Status changes are written to an outbox (WebhookDelivery) in the same transaction as the
change, then sent after commit. Anything that fails is retried by
`python manage.py send_kikapu_webhooks` (run it from cron every minute).
Updates for one order are always delivered in order: a later update waits for an earlier one.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ReplyDelivery, WebhookDelivery

logger = logging.getLogger(__name__)

NOTIFY_STATUSES = {"confirmed", "dispatched", "delivered", "cancelled"}


def _setting(name, default=""):
    return getattr(settings, name, default)


def build_payload(order, status, note):
    return {
        "kikapu_order_id": order.external_order_id,
        "mkulima_order_id": order.order_number,
        "status": status,
        "note": note or "",
        "updated_at": timezone.now().isoformat().replace("+00:00", "Z"),
    }


def sign(secret, timestamp, body):
    """Hex HMAC-SHA256 of `timestamp + "." + raw_body`."""
    return hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + body, hashlib.sha256).hexdigest()


def queue_status_update(sender, order, status, note="", **kwargs):
    """Receiver for inputs.signals.farmer_order_status_changed."""
    if order.channel != "kikapu" or status not in NOTIFY_STATUSES:
        return
    WebhookDelivery.objects.create(order=order, status=status, payload=build_payload(order, status, note))
    order_id = order.pk
    transaction.on_commit(lambda: deliver_pending(order_id=order_id))


def deliver_pending(order_id=None, now=None):
    """Send due updates. Returns (sent, failed) counts."""
    now = now or timezone.now()
    pending = WebhookDelivery.objects.filter(delivered_at__isnull=True, gave_up=False)
    if order_id is not None:
        pending = pending.filter(order_id=order_id)

    sent = failed = 0
    for oid in pending.values_list("order_id", flat=True).distinct():
        for delivery in pending.filter(order_id=oid).order_by("created_at", "pk"):
            if delivery.next_attempt_at > now:
                break  # keep this order's updates in sequence
            if _send(delivery, now):
                sent += 1
            else:
                failed += 1
                break
    return sent, failed


def _send(delivery, now, url=None):
    url = url or _setting("KIKAPU_BRIDGE_WEBHOOK_URL")
    secret = _setting("KIKAPU_BRIDGE_WEBHOOK_SECRET")
    if not url or not secret:
        # Not configured yet: keep it queued without using up attempts.
        delivery.last_error = "Webhook URL or secret not configured."
        delivery.save(update_fields=["last_error"])
        return False

    body = json.dumps(delivery.payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-Partner-ID": _setting("KIKAPU_BRIDGE_PARTNER_ID", "mkulima-smart"),
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": sign(secret, timestamp, body),
    }
    outbound_token = _setting("KIKAPU_BRIDGE_OUTBOUND_TOKEN")
    if outbound_token:
        headers["Authorization"] = f"Bearer {outbound_token}"

    delivery.attempts += 1
    try:
        response = requests.post(url, data=body, headers=headers, timeout=_setting("KIKAPU_BRIDGE_WEBHOOK_TIMEOUT", 5))
        delivery.last_response_code = response.status_code
        ok = 200 <= response.status_code < 300
        delivery.last_error = "" if ok else f"HTTP {response.status_code}: {response.text[:200]}"
    except requests.RequestException as exc:
        ok = False
        delivery.last_response_code = None
        delivery.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"

    if ok:
        delivery.delivered_at = now
    else:
        # 1, 2, 4 … minutes, capped at an hour.
        delivery.next_attempt_at = now + timedelta(minutes=min(2 ** (delivery.attempts - 1), 60))
        delivery.gave_up = delivery.attempts >= type(delivery).MAX_ATTEMPTS
        logger.warning("Kikapu webhook %s failed: %s", delivery, delivery.last_error)
    delivery.save()
    return ok


# ---------------------------------------------------------------------------
# Chat replies (agronomist or AI answers that arrive after the farmer's request has finished)
# ---------------------------------------------------------------------------

def build_reply_payload(message, conversation, source, agronomist=None, text=None):
    """`reply_id` lets Kikapu ignore a repeat delivery of the same reply."""
    return {
        "event": "assistant.reply",
        "reply_id": f"MSR-{message.pk}",
        "phone_number": conversation.phone_number,
        "conversation_id": conversation.pk,
        "language": conversation.language,
        "text": text or message.text,
        "source": source,  # "agronomist" or "ai"
        "agronomist": agronomist,
        "sent_at": timezone.now().isoformat().replace("+00:00", "Z"),
    }


def queue_reply(message, conversation, source, agronomist=None, text=None):
    """Write the reply to the outbox and send it once the surrounding transaction commits."""
    delivery = ReplyDelivery.objects.create(
        message=message, phone_number=conversation.phone_number,
        payload=build_reply_payload(message, conversation, source, agronomist, text),
    )
    phone = conversation.phone_number
    transaction.on_commit(lambda: deliver_replies(phone_number=phone))
    return delivery


def deliver_replies(phone_number=None, now=None):
    """Send due replies. Returns (sent, failed). Replies to one farmer keep their order."""
    now = now or timezone.now()
    url = _setting("KIKAPU_BRIDGE_REPLY_URL")
    pending = ReplyDelivery.objects.filter(delivered_at__isnull=True, gave_up=False)
    if phone_number is not None:
        pending = pending.filter(phone_number=phone_number)

    sent = failed = 0
    for phone in pending.values_list("phone_number", flat=True).distinct():
        for delivery in pending.filter(phone_number=phone).order_by("created_at", "pk"):
            if delivery.next_attempt_at > now:
                break
            if _send(delivery, now, url=url):
                sent += 1
            else:
                failed += 1
                break
    return sent, failed

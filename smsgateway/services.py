"""Taking in messages from a phone, deciding what each one means, and queueing the reply."""
import logging
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import handlers, outbox, text
from .models import Contact, InboundSms

logger = logging.getLogger("smsgateway")

MAX_PROCESS_ATTEMPTS = 3
SENDER_LIMIT_PER_HOUR = 30


# ---------------------------------------------------------------------------
# Receiving
# ---------------------------------------------------------------------------

def _when(value):
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _sender(raw):
    """A phone number as +255..., or the sender id as it came (MPESA, Vodacom) which we can read but never answer."""
    raw = (raw or "").strip()
    return text.e164(raw) or raw[:20].upper()


def store_inbound(device, items):
    """
    Save a batch from the phone. Returns one result per item in the same order:
    accepted (stored), duplicate (stored earlier), or rejected (refused for good, with a reason).
    Messages that can be answered quickly are answered straight away; the rest wait for the worker.
    """
    results = []
    allowed = {text.e164(n) or n for n in (device.allowed_senders or [])}
    for item in items:
        client_id = str(item.get("client_id") or "").strip()[:64] if isinstance(item, dict) else ""
        if not client_id:
            results.append({"client_id": client_id, "status": "rejected", "reason": "missing_client_id"})
            continue
        sender = _sender(item.get("from"))
        body = item.get("body")
        if not sender:
            results.append({"client_id": client_id, "status": "rejected", "reason": "missing_from"})
            continue
        if not isinstance(body, str):
            results.append({"client_id": client_id, "status": "rejected", "reason": "missing_body"})
            continue
        if allowed and sender not in allowed:
            results.append({"client_id": client_id, "status": "rejected", "reason": "sender_not_allowed"})
            continue
        try:
            with transaction.atomic():
                sms = InboundSms.objects.create(
                    device=device, client_id=client_id, sender=sender, body=body,
                    sent_at=_when(item.get("sent_at")), received_at=_when(item.get("received_at")),
                    sim_slot=item.get("sim_slot") if isinstance(item.get("sim_slot"), int) else None,
                    parts=item.get("parts") if isinstance(item.get("parts"), int) and item["parts"] > 0 else 1,
                )
        except IntegrityError:
            results.append({"client_id": client_id, "status": "duplicate", "id": InboundSms.objects.get(device=device, client_id=client_id).pk})
            continue
        results.append({"client_id": client_id, "status": "accepted", "id": sms.pk})
        try:
            process(sms, inline=True)
        except Exception:  # never fail the upload because of a bug in understanding a message; the worker retries it
            logger.exception("Could not process SMS %s", sms.pk)
            InboundSms.objects.filter(pk=sms.pk, status=InboundSms.RECEIVED).update(status=InboundSms.PENDING)
    return results


# ---------------------------------------------------------------------------
# Understanding and answering
# ---------------------------------------------------------------------------

def _finish(sms, status, handler="", note=""):
    InboundSms.objects.filter(pk=sms.pk).update(status=status, handler=handler, note=note[:200])


def process(sms, *, inline=True):
    """
    Work out what the message means and queue the reply. With inline=True slow handlers (those that may call the AI)
    are only marked as waiting, so the phone's upload is not held up; the background worker answers them.
    """
    project = handlers.PROJECTS.get(sms.device.project)
    if project is None:
        return _finish(sms, InboundSms.IGNORED, note=f"no handler for project {sms.device.project}")
    if not text.e164(sms.sender):
        return _finish(sms, InboundSms.IGNORED, note="sender is not a phone number")

    contact, _ = Contact.objects.get_or_create(phone=sms.sender)
    Contact.objects.filter(pk=contact.pk).update(last_message_at=timezone.now())

    name, args = handlers.parse(project["keywords"], sms.body)
    if contact.opted_out and name not in project["allowed_when_opted_out"]:
        return _finish(sms, InboundSms.IGNORED, handler=name, note="opted out")
    recent = InboundSms.objects.filter(sender=sms.sender, created_at__gte=timezone.now() - timedelta(hours=1)).count()
    if recent > SENDER_LIMIT_PER_HOUR:
        return _finish(sms, InboundSms.IGNORED, handler=name, note="too many messages this hour")

    if name in project["deferred"] and inline:
        return InboundSms.objects.filter(pk=sms.pk).update(status=InboundSms.PENDING, handler=name)

    handler = project["handlers"][name]
    try:
        reply = handler(sms, contact, args)
    except Exception:
        logger.exception("Handler %s failed for SMS %s", name, sms.pk)
        InboundSms.objects.filter(pk=sms.pk).update(status=InboundSms.PENDING, handler=name, attempts=sms.attempts + 1, note="error, will retry")
        return
    _finish(sms, InboundSms.PROCESSED, handler=name)
    if reply:
        outbox.send_sms(sms.sender, reply, in_reply_to=sms, handler=name, force=(name in project["allowed_when_opted_out"] or name == "stop"))


def process_pending(limit=20):
    """Answer the messages that were waiting (the slow ones). Called by the background worker."""
    done = gave_up = 0
    for sms in InboundSms.objects.filter(status=InboundSms.PENDING).select_related("device").order_by("id")[:limit]:
        if sms.attempts >= MAX_PROCESS_ATTEMPTS:
            _finish(sms, InboundSms.IGNORED, handler=sms.handler, note="gave up after errors")
            gave_up += 1
            continue
        try:
            process(sms, inline=False)
            done += 1
        except Exception:
            logger.exception("Could not process SMS %s", sms.pk)
            InboundSms.objects.filter(pk=sms.pk).update(attempts=sms.attempts + 1)
    return {"answered": done, "gave_up": gave_up}

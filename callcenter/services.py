"""
The call center's rules. A farmer message is routed like this:

    chat already with an agronomist or waiting for one  -> keep it there, say nothing new
    chat the AI took over a moment ago                  -> the AI keeps answering
    nobody online                                       -> the AI answers straight away (no waiting)
    someone online                                      -> open a case, tell the farmer an agronomist is coming

`sweep()` (run by `manage.py run_callcenter`) does the timed parts: when nobody accepts a waiting case in
CALLCENTER_ACCEPT_SECONDS the AI answers; an agronomist who goes quiet loses the chat.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from assistant import engine
from assistant.models import Message
from gova_pp.diagnosis import DiagnosisError
from kikapu_bridge.webhooks import queue_reply

from .models import Agronomist, Case, setting

logger = logging.getLogger("callcenter")


def enabled():
    return bool(getattr(settings, "CALLCENTER_ENABLED", False))


def _language(conversation):
    return conversation.language if conversation.language in engine.STRINGS else "sw"


# ---------------------------------------------------------------------------
# Routing a farmer message
# ---------------------------------------------------------------------------

def active_case(conversation):
    case = conversation.cases.filter(status__in=Case.ACTIVE).order_by("-created_at").first()
    if case and case.status == Case.AI:
        sticky = timedelta(minutes=setting("CALLCENTER_AI_STICKY_MINUTES", 30))
        if timezone.now() - case.last_activity_at > sticky:
            Case.objects.filter(pk=case.pk).update(status=Case.CLOSED, closed_at=timezone.now())
            return None
    return case


def _queued(conversation, handled_by, acknowledgement=""):
    return {
        "conversation_id": conversation.pk,
        "message_id": None,
        "reply_text": acknowledgement,
        "language": _language(conversation),
        "diagnosis": None,
        "products": [],
        "needs_expert": False,
        "duplicate": False,
        "rate_limited": False,
        "queued": True,
        "handled_by": handled_by,
    }


def route_incoming(conversation, inbound, language):
    """Return a result dict when a person will answer (the AI must stay quiet), or None to let the AI answer now."""
    if not enabled():
        return None

    case = active_case(conversation)
    now = timezone.now()
    if case is not None:
        Case.objects.filter(pk=case.pk).update(last_activity_at=now)
        if case.status == Case.AI:
            return None
        return _queued(conversation, "agronomist" if case.status == Case.OPEN else "waiting")

    if not Agronomist.online().exists():
        return None

    Case.objects.create(conversation=conversation)
    return _queued(conversation, "waiting", acknowledgement=engine.fallback_text("connecting", language))


# ---------------------------------------------------------------------------
# What agronomists do
# ---------------------------------------------------------------------------

def accept(case_id, agronomist):
    """First agronomist to call this wins. Also takes over a chat the AI is handling."""
    now = timezone.now()
    return Case.objects.filter(pk=case_id, status__in=[Case.WAITING, Case.AI]).update(
        status=Case.OPEN, agronomist=agronomist, accepted_at=now, last_activity_at=now,
    ) == 1


def _owned_open_case(case_id, agronomist):
    case = Case.objects.select_related("conversation").get(pk=case_id)
    if case.status != Case.OPEN or case.agronomist_id != agronomist.pk:
        raise PermissionDenied("This chat is not yours.")
    return case


def reply(case_id, agronomist, text):
    """Store an agronomist's answer and queue it for the farmer's WhatsApp. Returns the stored Message."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Write a reply first.")
    text = text[:1500]
    with transaction.atomic():
        case = _owned_open_case(case_id, agronomist)
        conversation = case.conversation
        last_farmer = conversation.messages.filter(role="farmer").order_by("-pk").first()
        company = agronomist.company_name
        message = Message.objects.create(
            conversation=conversation, role="agronomist", kind="text", text=text, in_reply_to=last_farmer,
            payload={"agronomist_id": agronomist.pk, "name": agronomist.full_name, "company": company},
        )
        now = timezone.now()
        Case.objects.filter(pk=case.pk).update(last_activity_at=now)
        conversation.last_message_at = now
        conversation.needs_expert = False
        conversation.save()
        signature = f"- {agronomist.full_name}" + (f", {company}" if company else "")
        queue_reply(
            message, conversation, "agronomist",
            agronomist={"name": agronomist.full_name, "company": company},
            text=f"{text}\n\n{signature}",
        )
    return message


def release(case_id, agronomist):
    """Give the chat back so another agronomist (or, after the wait, the AI) can take it."""
    _owned_open_case(case_id, agronomist)
    now = timezone.now()
    Case.objects.filter(pk=case_id).update(status=Case.WAITING, agronomist=None, waiting_since=now, last_activity_at=now)


def close(case_id, agronomist):
    _owned_open_case(case_id, agronomist)
    now = timezone.now()
    Case.objects.filter(pk=case_id).update(status=Case.CLOSED, closed_at=now, last_activity_at=now)


def hand_to_ai(case_id, agronomist):
    _owned_open_case(case_id, agronomist)
    return answer_with_ai(Case.objects.get(pk=case_id), allowed=[Case.OPEN])


# ---------------------------------------------------------------------------
# The AI covers
# ---------------------------------------------------------------------------

def _unanswered(conversation):
    """Farmer messages written since anyone last replied."""
    last = conversation.messages.exclude(role="farmer").order_by("-pk").first()
    pending = conversation.messages.filter(role="farmer")
    return pending.filter(pk__gt=last.pk) if last else pending


def answer_with_ai(case, allowed=(Case.WAITING,)):
    """Have the AI answer what the farmer is waiting on. Returns True when it did (False if someone took the chat first)."""
    now = timezone.now()
    claimed = Case.objects.filter(pk=case.pk, status__in=list(allowed)).update(
        status=Case.AI, agronomist=None, answered_by_ai=True, last_activity_at=now,
    )
    if claimed != 1:
        return False

    conversation = case.conversation
    language = _language(conversation)
    pending = _unanswered(conversation)
    inbound = pending.filter(kind="image").order_by("-pk").first() or pending.order_by("-pk").first()
    if inbound is None:
        return True  # the farmer was already answered some other way
    try:
        message = engine.respond(conversation, inbound, language)
    except DiagnosisError as exc:
        kind = "err_image" if exc.status in (400, 404) else "err_service"
        message = _apology(conversation, inbound, kind, language)
    except Exception:
        logger.exception("AI answer for case %s failed", case.pk)
        message = _apology(conversation, inbound, "err_service", language)
    queue_reply(message, conversation, "ai")
    return True


def _apology(conversation, inbound, kind, language):
    return Message.objects.create(
        conversation=conversation, role="assistant", kind="text", text=engine.fallback_text(kind, language), in_reply_to=inbound,
    )


# ---------------------------------------------------------------------------
# Timers
# ---------------------------------------------------------------------------

def sweep(now=None):
    """Apply the timeouts. Returns a dict of counts."""
    now = now or timezone.now()
    counts = {"ai": 0, "released": 0, "closed": 0}
    accept_wait = timedelta(seconds=setting("CALLCENTER_ACCEPT_SECONDS", 120))
    reply_wait = timedelta(seconds=setting("CALLCENTER_REPLY_SECONDS", 600))
    sticky = timedelta(minutes=setting("CALLCENTER_AI_STICKY_MINUTES", 30))

    # An agronomist who went quiet loses the chat; it goes back to the queue with a fresh timer.
    for case in Case.objects.filter(status=Case.OPEN).select_related("conversation"):
        waiting_on_us = _unanswered(case.conversation).order_by("pk").first()
        if waiting_on_us and now - waiting_on_us.created_at > reply_wait:
            Case.objects.filter(pk=case.pk, status=Case.OPEN).update(
                status=Case.WAITING, agronomist=None, waiting_since=now,
            )
            counts["released"] += 1
        elif now - case.last_activity_at > timedelta(hours=24):
            Case.objects.filter(pk=case.pk).update(status=Case.CLOSED, closed_at=now)
            counts["closed"] += 1

    # Nobody accepted in time, or nobody is online any more: the AI answers.
    anyone_online = Agronomist.online().exists()
    for case in Case.objects.filter(status=Case.WAITING).select_related("conversation").order_by("waiting_since"):
        if not anyone_online or now - case.waiting_since >= accept_wait:
            if answer_with_ai(case):
                counts["ai"] += 1

    stale_ai = Case.objects.filter(status=Case.AI, last_activity_at__lt=now - sticky)
    counts["closed"] += stale_ai.update(status=Case.CLOSED, closed_at=now)
    return counts

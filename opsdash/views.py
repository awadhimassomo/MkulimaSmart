"""
Operations dashboard for administrators: one place to see what needs attention and to run the people side of
the platform (government officers, agronomists, farmer chats, undelivered replies) without the Django admin.
Superusers only.
"""
import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from urllib.parse import quote
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_POST

from assistant.models import Conversation
from callcenter.models import Agronomist, Case, Heartbeat, Invite
from gova_pp.models import FarmerMessage, GovernmentOfficial
from operations.models import InputSeller
from kikapu_bridge.models import ReplyDelivery, WebhookDelivery

User = get_user_model()
logger = logging.getLogger("opsdash")
WORKER_STALE_SECONDS = 90


def ops_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("gova_pp:login")
        if not request.user.is_superuser:
            return render(request, "opsdash/forbidden.html", status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


def _age(seconds):
    if seconds is None:
        return "never"
    if seconds < 90:
        return f"{seconds}s ago"
    if seconds < 5400:
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} h ago"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@ops_required
def overview(request):
    now = timezone.now()
    day = now - timedelta(hours=24)
    accept_wait = getattr(settings, "CALLCENTER_ACCEPT_SECONDS", 120)
    enabled = bool(getattr(settings, "CALLCENTER_ENABLED", False))

    worker_age = Heartbeat.age_seconds()
    worker_ok = worker_age is not None and worker_age <= WORKER_STALE_SECONDS

    waiting = Case.objects.filter(status=Case.WAITING)
    overdue = waiting.filter(waiting_since__lt=now - timedelta(seconds=accept_wait * 2))
    stuck_replies = ReplyDelivery.objects.filter(delivered_at__isnull=True)
    failed_replies = stuck_replies.filter(gave_up=True)
    failed_orders = WebhookDelivery.objects.filter(delivered_at__isnull=True, gave_up=True)
    unanswered_experts = Conversation.objects.filter(needs_expert=True, last_message_at__gte=day).exclude(
        cases__status=Case.OPEN, cases__agronomist__isnull=False,
    )
    pending_officials = GovernmentOfficial.objects.filter(status=GovernmentOfficial.PENDING)

    attention = []
    if pending_officials.exists():
        attention.append({"level": "warn", "text": f"{pending_officials.count()} government request(s) waiting for approval", "url": "gova_pp:officials"})
    if enabled and not worker_ok:
        attention.append({"level": "bad", "text": f"The call center worker is not running (last seen {_age(worker_age)}). Farmers may wait without an answer.", "url": "ops:deliveries"})
    if overdue.exists():
        attention.append({"level": "bad", "text": f"{overdue.count()} farmer chat(s) have waited far longer than expected", "url": "ops:chats", "query": "?state=waiting"})
    if failed_replies.exists() or failed_orders.exists():
        attention.append({"level": "bad", "text": f"{failed_replies.count() + failed_orders.count()} message(s) to Kikapu failed for good", "url": "ops:deliveries"})
    elif stuck_replies.exists():
        attention.append({"level": "warn", "text": f"{stuck_replies.count()} reply(ies) not yet delivered to Kikapu", "url": "ops:deliveries"})
    if unanswered_experts.exists():
        attention.append({"level": "warn", "text": f"{unanswered_experts.count()} farmer(s) in the last 24 hours were told to see an expert", "url": "ops:chats", "query": "?state=expert"})

    online = Agronomist.online()
    context = {
        "enabled": enabled,
        "worker_ok": worker_ok,
        "worker_age": _age(worker_age),
        "attention": attention,
        "farmers": User.objects.filter(is_farmer=True).count(),
        "new_farmers": User.objects.filter(is_farmer=True, date_joined__gte=now - timedelta(days=7)).count(),
        "officials_active": GovernmentOfficial.objects.filter(status=GovernmentOfficial.APPROVED).count(),
        "officials_pending": pending_officials.count(),
        "agronomists_total": Agronomist.objects.filter(is_active=True).count(),
        "agronomists_online": online.count(),
        "waiting": waiting.count(),
        "open_cases": Case.objects.filter(status=Case.OPEN).count(),
        "ai_24h": Case.objects.filter(status=Case.AI, last_activity_at__gte=day).count(),
        "chats_24h": Conversation.objects.filter(last_message_at__gte=day).count(),
        "messages_new": FarmerMessage.objects.filter(status="new").count(),
        "messages_urgent": FarmerMessage.objects.filter(priority="urgent").exclude(status__in=["resolved", "archived"]).count(),
    }
    context["nav"] = "overview"
    return render(request, "opsdash/overview.html", context)


# ---------------------------------------------------------------------------
# Agronomists
# ---------------------------------------------------------------------------

@ops_required
def agronomists(request):
    rows = (
        Agronomist.objects.select_related("user", "company")
        .annotate(
            open_chats=Count("cases", filter=Q(cases__status=Case.OPEN), distinct=True),
            handled=Count("cases", distinct=True),
            last_reply=Max("cases__last_activity_at"),
        )
        .order_by("-is_active", "company__business_name", "full_name")
    )
    invites = [
        {"invite": invite, "link": request.build_absolute_uri(reverse("callcenter:join", args=[invite.token]))}
        for invite in Invite.objects.filter(used_at__isnull=True, expires_at__gt=timezone.now()).select_related("company")
    ]
    companies = InputSeller.objects.filter(is_active=True, onboarding_completed=True).exclude(seller_type="agro_input_dealer").order_by("business_name", "seller_name")
    return render(request, "opsdash/agronomists.html", {"rows": rows, "invites": invites, "companies": companies, "nav": "agronomists"})


@ops_required
@require_POST
def invite_create(request):
    """An administrator invites an agronomist on behalf of an input company or shop."""
    company = (
        InputSeller.objects.filter(pk=request.POST.get("company") or 0, is_active=True, onboarding_completed=True)
        .exclude(seller_type="agro_input_dealer").first()
    )
    if company is None:
        messages.error(request, "Choose the manufacturer or supplier this agronomist works for. Agrovets (retail shops) do not have agronomists.")
        return redirect("ops:agronomists")
    Invite.objects.create(company=company, name=request.POST.get("name", "").strip()[:120], created_by=request.user)
    messages.success(request, "Invite link created. Copy it from the list below and send it to the agronomist.")
    return redirect("ops:agronomists")


@ops_required
@require_POST
def invite_revoke(request, pk):
    get_object_or_404(Invite, pk=pk, used_at__isnull=True).delete()
    return redirect("ops:agronomists")


@ops_required
@require_POST
def agronomist_toggle(request, pk):
    agronomist = get_object_or_404(Agronomist, pk=pk)
    agronomist.is_active = not agronomist.is_active
    if not agronomist.is_active:
        agronomist.is_available = False
        now = timezone.now()
        Case.objects.filter(agronomist=agronomist, status=Case.OPEN).update(
            status=Case.WAITING, agronomist=None, waiting_since=now, last_activity_at=now,
        )
    agronomist.save(update_fields=["is_active", "is_available"])
    messages.success(request, f"{agronomist.full_name}: access {'on' if agronomist.is_active else 'off'}.")
    return redirect("ops:agronomists")


# ---------------------------------------------------------------------------
# Farmer chats (the crop doctor / call center conversations)
# ---------------------------------------------------------------------------

STATES = [
    ("", "All"), ("waiting", "Waiting for an agronomist"), ("open", "With an agronomist"),
    ("ai", "Answered by the AI"), ("expert", "Told to see an expert"),
]


@ops_required
def chats(request):
    state = request.GET.get("state", "")
    term = request.GET.get("q", "").strip()
    rows = Conversation.objects.annotate(
        message_count=Count("messages", distinct=True),
        active_status=Max("cases__status", filter=Q(cases__status__in=Case.ACTIVE)),
    )
    if state in (Case.WAITING, Case.OPEN, Case.AI):
        rows = rows.filter(cases__status=state).distinct()
    elif state == "expert":
        rows = rows.filter(needs_expert=True)
    if term:
        rows = rows.filter(Q(farmer_name__icontains=term) | Q(phone_number__icontains=term) | Q(region__icontains=term))
    page = Paginator(rows.order_by("-last_message_at"), 25).get_page(request.GET.get("page"))
    return render(request, "opsdash/chats.html", {"page": page, "states": STATES, "state": state, "term": term, "nav": "chats"})


@ops_required
def chat_detail(request, pk):
    conversation = get_object_or_404(Conversation, pk=pk)
    return render(request, "opsdash/chat_detail.html", {
        "nav": "chats",
        "conversation": conversation,
        "messages_list": conversation.messages.all(),
        "cases": conversation.cases.select_related("agronomist", "agronomist__company"),
    })


# ---------------------------------------------------------------------------
# Messages to Kikapu that did not arrive
# ---------------------------------------------------------------------------

@ops_required
def deliveries(request):
    worker_age = Heartbeat.age_seconds()
    return render(request, "opsdash/deliveries.html", {
        "nav": "deliveries",
        "replies": ReplyDelivery.objects.filter(delivered_at__isnull=True).select_related("message")[:100],
        "orders": WebhookDelivery.objects.filter(delivered_at__isnull=True).select_related("order")[:100],
        "worker_age": _age(worker_age),
        "worker_ok": worker_age is not None and worker_age <= WORKER_STALE_SECONDS,
        "enabled": bool(getattr(settings, "CALLCENTER_ENABLED", False)),
    })


@ops_required
@require_POST
def delivery_retry(request, kind, pk):
    model = {"reply": ReplyDelivery, "order": WebhookDelivery}.get(kind)
    if model is None:
        return redirect("ops:deliveries")
    model.objects.filter(pk=pk, delivered_at__isnull=True).update(gave_up=False, attempts=0, next_attempt_at=timezone.now())
    messages.success(request, "Queued to try again. The background worker sends it within a few seconds.")
    return redirect("ops:deliveries")


# ---------------------------------------------------------------------------
# Accounts: find someone and give them a link to set a new password
# ---------------------------------------------------------------------------

def _reset_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return request.build_absolute_uri(reverse("website:password_reset_confirm", kwargs={"uidb64": uid, "token": token}))


@ops_required
def accounts(request, reset_for=None, link=None):
    term = request.GET.get("q", "").strip()
    people = User.objects.none()
    if term:
        people = User.objects.filter(
            Q(email__icontains=term) | Q(phone_number__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)
        ).order_by("email")[:25]
    return render(request, "opsdash/accounts.html", {
        "nav": "accounts", "term": term, "people": people, "reset_for": reset_for, "link": link,
        "valid_days": max(1, getattr(settings, "PASSWORD_RESET_TIMEOUT", 259200) // 86400),
    })


@ops_required
@require_POST
def account_reset_link(request, pk):
    """A one-time link the person opens to choose a new password. The administrator never sees or sets the password."""
    user = get_object_or_404(User, pk=pk)
    logger.info("Password reset link created for user %s by %s", user.pk, request.user.pk)
    request.GET = request.GET.copy()
    request.GET["q"] = user.email or user.phone_number or ""
    return accounts(request, reset_for=user, link=_reset_link(request, user))


@ops_required
@require_POST
def account_reset_email(request, pk):
    """Email the person a one-time link to choose a new password (the same email the Forgot password page sends)."""
    user = get_object_or_404(User, pk=pk)
    back = f"{reverse('ops:accounts')}?q={quote(user.email or user.phone_number or '')}"
    if not user.email:
        messages.error(request, "This account has no email address. Copy a reset link instead and send it yourself.")
        return redirect(back)
    context = {
        "user": user,
        "protocol": "https" if request.is_secure() else "http",
        "domain": request.get_host(),
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }
    subject = "".join(render_to_string("auth/emails/password_reset_subject.txt", context).splitlines())
    body = render_to_string("auth/emails/password_reset_email.txt", context)
    try:
        send_mail(subject, body, None, [user.email], fail_silently=False)
    except Exception:
        logger.exception("Reset email to user %s could not be sent", user.pk)
        messages.error(request, "The email could not be sent. Check the email settings on the server, or copy a reset link and send it yourself.")
    else:
        logger.info("Password reset email sent to user %s by %s", user.pk, request.user.pk)
        messages.success(request, f"A reset email was sent to {user.email}.")
    return redirect(back)

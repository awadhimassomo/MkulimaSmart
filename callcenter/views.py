import logging
import re
from datetime import timedelta
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from assistant.models import Message
from operations.models import InputSeller

from . import services
from .models import Agronomist, Case, Invite

User = get_user_model()
logger = logging.getLogger("callcenter")


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def agronomist_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        profile = Agronomist.objects.select_related("company").filter(user=request.user, is_active=True).first()
        if profile is None:
            return render(request, "callcenter/not_agronomist.html", status=403)
        request.agronomist = profile
        return view_func(request, *args, **kwargs)

    return wrapped


def company_required(view_func):
    """The input company or shop that owns the team (its business profile must be set up)."""

    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        company = InputSeller.objects.filter(user=request.user, onboarding_completed=True).first()
        if company is None:
            messages.info(request, "Set up your business profile first.")
            return redirect("marketplace:supplier_onboarding")
        if not company.can_have_agronomists:
            messages.info(request, "Agronomists are for manufacturers and suppliers. Your agrovet dashboard has the POS, your stock, and ordering stock from suppliers.")
            return redirect("inputs:home")
        request.company = company
        return view_func(request, *args, **kwargs)

    return wrapped


def mask_phone(phone):
    digits = "".join(c for c in phone if c.isdigit())
    return f"+{digits[:3]} *** *** {digits[-3:]}" if len(digits) >= 9 else "hidden"


def can_see(agronomist, case):
    """Agronomists see chats that are waiting or with the AI, and their own. Never another agronomist's chat."""
    if case.status in (Case.WAITING, Case.AI):
        return True
    return case.agronomist_id == agronomist.pk


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

def _summary(case):
    conversation = case.conversation
    last = conversation.messages.filter(role="farmer").order_by("-pk").first()
    preview = ""
    if last is not None:
        preview = last.text or ("Photo" if last.kind == "image" else "")
    now = timezone.now()
    return {
        "id": case.pk,
        "farmer": conversation.farmer_name or mask_phone(conversation.phone_number),
        "region": conversation.region,
        "preview": preview[:120],
        "has_photo": bool(last and last.kind == "image"),
        "waited": int((now - case.waiting_since).total_seconds()),
        "status": case.status,
        "url": reverse("callcenter:case", args=[case.pk]),
        "accept_url": reverse("callcenter:case_accept", args=[case.pk]),
    }


@agronomist_required
def console(request):
    request.agronomist.touch()
    from trainingdata import services as training

    return render(request, "callcenter/console.html", {
        "agronomist": request.agronomist, "to_label": training.labelable().count(), "call_center_on": services.enabled(),
    })


@agronomist_required
def state(request):
    agronomist = request.agronomist
    agronomist.touch()
    cases = Case.objects.select_related("conversation")
    since = timezone.now() - timedelta(hours=24)
    return JsonResponse({
        "available": agronomist.is_available,
        "waiting": [_summary(c) for c in cases.filter(status=Case.WAITING).order_by("waiting_since")],
        "mine": [_summary(c) for c in cases.filter(status=Case.OPEN, agronomist=agronomist).order_by("-last_activity_at")],
        "ai": [_summary(c) for c in cases.filter(status=Case.AI, last_activity_at__gte=since).order_by("-last_activity_at")[:20]],
    })


@agronomist_required
@require_POST
def availability(request):
    agronomist = request.agronomist
    agronomist.is_available = request.POST.get("available") == "1"
    agronomist.last_seen = timezone.now()
    agronomist.save(update_fields=["is_available", "last_seen"])
    return JsonResponse({"available": agronomist.is_available})


# ---------------------------------------------------------------------------
# One chat
# ---------------------------------------------------------------------------

def _case_for(request, pk):
    case = get_object_or_404(Case.objects.select_related("conversation", "agronomist"), pk=pk)
    if not can_see(request.agronomist, case):
        raise PermissionDenied
    return case


def _message_json(message):
    return {
        "id": message.pk,
        "role": message.role,
        "text": message.text,
        "photo": message.photo.url if message.photo else (message.image_url or ""),
        "at": timezone.localtime(message.created_at).strftime("%H:%M"),
        "name": (message.payload or {}).get("name", "") if message.role == "agronomist" else "",
    }


@agronomist_required
def case_detail(request, pk):
    case = _case_for(request, pk)
    request.agronomist.touch()
    conversation = case.conversation
    return render(request, "callcenter/case.html", {
        "case": case,
        "conversation": conversation,
        "farmer": conversation.farmer_name or mask_phone(conversation.phone_number),
        "diagnosis": conversation.last_diagnosis,
        "mine": case.status == Case.OPEN and case.agronomist_id == request.agronomist.pk,
        "agronomist": request.agronomist,
    })


@agronomist_required
def case_messages(request, pk):
    case = _case_for(request, pk)
    request.agronomist.touch()
    after = int(request.GET.get("after") or 0)
    items = case.conversation.messages.filter(pk__gt=after).order_by("pk")
    return JsonResponse({
        "status": case.status,
        "mine": case.status == Case.OPEN and case.agronomist_id == request.agronomist.pk,
        "taken_by": case.agronomist.full_name if case.agronomist_id and case.agronomist_id != request.agronomist.pk else "",
        "messages": [_message_json(m) for m in items],
    })


@agronomist_required
@require_POST
def case_accept(request, pk):
    if services.accept(pk, request.agronomist):
        return JsonResponse({"ok": True, "url": reverse("callcenter:case", args=[pk])})
    return JsonResponse({"ok": False, "error": "Another agronomist already took this chat."}, status=409)


@agronomist_required
@require_POST
def case_reply(request, pk):
    try:
        message = services.reply(pk, request.agronomist, request.POST.get("text", ""))
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except PermissionDenied:
        return JsonResponse({"ok": False, "error": "This chat is no longer yours."}, status=403)
    return JsonResponse({"ok": True, "message": _message_json(message)})


def _simple_action(action):
    @agronomist_required
    @require_POST
    def view(request, pk):
        try:
            action(pk, request.agronomist)
        except PermissionDenied:
            return JsonResponse({"ok": False, "error": "This chat is no longer yours."}, status=403)
        return JsonResponse({"ok": True, "url": reverse("callcenter:console")})

    return view


case_release = _simple_action(services.release)
case_close = _simple_action(services.close)
case_ai = _simple_action(services.hand_to_ai)


# ---------------------------------------------------------------------------
# Joining with an invite link
# ---------------------------------------------------------------------------

class JoinForm(forms.Form):
    full_name = forms.CharField(max_length=120, label="Your full name")
    email = forms.EmailField(label="Email (you sign in with this)")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Repeat password")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Sign in instead, then ask your company for a new link.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password") != data.get("password2"):
            self.add_error("password2", "The passwords do not match.")
        elif data.get("password"):
            try:
                validate_password(data["password"])
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return data


def _invalid_invite(request, invite, token):
    """Say which of the three things went wrong, so the person (and the support team) can act on it."""
    reason = "unknown" if invite is None else invite.state  # "used" or "expired"
    logger.warning("Agronomist invite refused (%s): token starting %s", reason, (token or "")[:6])
    return render(request, "callcenter/join_invalid.html", {"reason": reason, "invite": invite}, status=410)


def join(request, token):
    # Chat apps and email clients sometimes glue a full stop, bracket or space onto the end of a link.
    clean = re.sub(r"[^A-Za-z0-9_-]", "", token or "")
    invite = Invite.objects.select_related("company").filter(token=clean).first()
    if invite is None or not invite.usable:
        return _invalid_invite(request, invite, clean)

    form = JoinForm(request.POST or None, initial={"full_name": invite.name})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            if Invite.objects.filter(pk=invite.pk, used_at__isnull=True).update(used_at=timezone.now()) != 1:
                return _invalid_invite(request, Invite.objects.filter(pk=invite.pk).first(), clean)
            first, _, last = data["full_name"].strip().partition(" ")
            user = User.objects.create_user(password=data["password"], email=data["email"], first_name=first, last_name=last)
            agronomist = Agronomist.objects.create(user=user, company=invite.company, full_name=data["full_name"].strip())
            Invite.objects.filter(pk=invite.pk).update(agronomist=agronomist)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("callcenter:console")
    return render(request, "callcenter/join.html", {"form": form, "invite": invite, "company": invite.company})


# ---------------------------------------------------------------------------
# The company's team page
# ---------------------------------------------------------------------------

@company_required
def team(request):
    company = request.company
    invites = [
        {"invite": invite, "link": request.build_absolute_uri(reverse("callcenter:join", args=[invite.token]))}
        for invite in company.agronomist_invites.filter(used_at__isnull=True, expires_at__gt=timezone.now())
    ]
    earlier = (
        company.agronomist_invites.exclude(used_at__isnull=True, expires_at__gt=timezone.now())
        .select_related("agronomist")[:10]
    )
    return render(request, "callcenter/team.html", {
        "company": company,
        "agronomists": company.agronomists.select_related("user"),
        "invites": invites,
        "earlier": earlier,
    })


@company_required
@require_POST
def team_invite(request):
    Invite.objects.create(company=request.company, name=request.POST.get("name", "").strip()[:120], created_by=request.user)
    messages.success(request, "Invite link created. Copy it and send it to your agronomist.")
    return redirect("callcenter:team")


@company_required
@require_POST
def team_revoke(request, pk):
    get_object_or_404(Invite, pk=pk, company=request.company, used_at__isnull=True).delete()
    return redirect("callcenter:team")


@company_required
@require_POST
def team_toggle(request, pk):
    agronomist = get_object_or_404(Agronomist, pk=pk, company=request.company)
    agronomist.is_active = not agronomist.is_active
    if not agronomist.is_active:
        agronomist.is_available = False
        # Chats they were holding go back to the queue straight away.
        now = timezone.now()
        Case.objects.filter(agronomist=agronomist, status=Case.OPEN).update(
            status=Case.WAITING, agronomist=None, waiting_since=now, last_activity_at=now,
        )
    agronomist.save(update_fields=["is_active", "is_available"])
    return redirect("callcenter:team")

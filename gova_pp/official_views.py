"""
Government officers getting access to the dashboard.

  /gova-pp/join/<token>/   an administrator's invite link: sign up and you are in (the invite is the approval)
  /gova-pp/signup/         anyone can ask for access; nothing works until an administrator approves
  /gova-pp/officials/      administrators (superusers) approve or reject requests, send invites, suspend access
"""
from datetime import timedelta
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from operations.models import TANZANIA_REGIONS

from . import officials
from .models import GovernmentInvite, GovernmentOfficial

User = get_user_model()
INVITE_DAYS = 7
SIGNUPS_PER_HOUR = 5


def superuser_required(view_func):
    """Only administrators decide who gets in; ordinary government staff cannot approve each other."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("gova_pp:login")
        if not request.user.is_superuser:
            return render(request, "gova_pp/official_forbidden.html", status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class OfficialForm(forms.Form):
    full_name = forms.CharField(max_length=120, label="Full name")
    email = forms.EmailField(label="Work email (you sign in with this)")
    institution = forms.CharField(max_length=160, label="Ministry, council or office")
    job_title = forms.CharField(max_length=120, required=False, label="Job title")
    region = forms.ChoiceField(choices=[("", "Select region")] + list(TANZANIA_REGIONS), required=False, label="Region")
    district = forms.CharField(max_length=120, required=False, label="District")
    phone = forms.CharField(max_length=25, required=False, label="Phone number (optional)")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Repeat password")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Sign in, or ask an administrator to give it access.")
        return email

    def clean_phone(self):
        phone = "".join(c for c in self.cleaned_data.get("phone", "") if c.isdigit() or c == "+")
        if len(phone) > 15:
            raise forms.ValidationError("Enter a valid phone number, for example +255712345678.")
        if phone and User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("This phone number belongs to another account.")
        return phone

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


class SignupForm(OfficialForm):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), max_length=1000, label="Why do you need access?",
        help_text="For example: extension officer for Mbeya Rural, answering farmers' questions.",
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot: people leave it empty, bots fill it


def _create_official(data, status, via, invite_creator=None):
    first, _, last = data["full_name"].strip().partition(" ")
    user = User.objects.create_user(
        phone_number=data["phone"] or None, password=data["password"], email=data["email"], first_name=first, last_name=last,
    )
    official = GovernmentOfficial.objects.create(
        user=user, full_name=data["full_name"].strip(), institution=data["institution"].strip(), job_title=data["job_title"].strip(),
        region=data["region"], district=data["district"].strip(), phone=data["phone"], reason=data.get("reason", ""), via=via,
    )
    if status == GovernmentOfficial.APPROVED:
        officials.approve(official, invite_creator, note="Joined with an invite link.")
    return user, official


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")) if forwarded else request.META.get("REMOTE_ADDR", "")


# ---------------------------------------------------------------------------
# Asking for access (needs approval)
# ---------------------------------------------------------------------------

def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST":
        key = f"gov-signup:{_client_ip(request)}"
        attempts = cache.get(key, 0)
        if attempts >= SIGNUPS_PER_HOUR:
            messages.error(request, "Too many requests from this connection. Please try again later.")
        elif form.is_valid():
            if form.cleaned_data.get("website"):  # a bot: pretend it worked
                return render(request, "gova_pp/official_received.html")
            cache.set(key, attempts + 1, 3600)
            with transaction.atomic():
                _create_official(form.cleaned_data, GovernmentOfficial.PENDING, "signup")
            return render(request, "gova_pp/official_received.html")
    return render(request, "gova_pp/official_signup.html", {"form": form})


# ---------------------------------------------------------------------------
# Invite link (already approved by whoever sent it)
# ---------------------------------------------------------------------------

def join(request, token):
    invite = GovernmentInvite.objects.filter(token=token).first()
    if invite is None or not invite.usable:
        return render(request, "gova_pp/official_join_invalid.html", status=410)

    form = OfficialForm(request.POST or None, initial={"full_name": invite.name, "institution": invite.institution, "region": invite.region})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if GovernmentInvite.objects.filter(pk=invite.pk, used_at__isnull=True).update(used_at=timezone.now()) != 1:
                return render(request, "gova_pp/official_join_invalid.html", status=410)
            user, official = _create_official(form.cleaned_data, GovernmentOfficial.APPROVED, "invite", invite_creator=invite.created_by)
            GovernmentInvite.objects.filter(pk=invite.pk).update(official=official)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("gova_pp:dashboard")
    return render(request, "gova_pp/official_join.html", {"form": form, "invite": invite})


# ---------------------------------------------------------------------------
# Administrators
# ---------------------------------------------------------------------------

@superuser_required
def manage(request):
    regions = dict(TANZANIA_REGIONS)
    everyone = list(GovernmentOfficial.objects.select_related("user", "decided_by"))
    for official in everyone:
        official.region_name = regions.get(official.region, official.region)
    invites = [
        {"invite": invite, "link": request.build_absolute_uri(reverse("gova_pp:join", args=[invite.token]))}
        for invite in GovernmentInvite.objects.filter(used_at__isnull=True, expires_at__gt=timezone.now())
    ]
    return render(request, "gova_pp/officials.html", {
        "pending": [o for o in everyone if o.status == GovernmentOfficial.PENDING],
        "active": [o for o in everyone if o.status in (GovernmentOfficial.APPROVED, GovernmentOfficial.SUSPENDED)],
        "rejected": [o for o in everyone if o.status == GovernmentOfficial.REJECTED],
        "invites": invites,
        "regions": TANZANIA_REGIONS,
    })


@superuser_required
@require_POST
def decide(request, pk, action):
    official = get_object_or_404(GovernmentOfficial.objects.select_related("user"), pk=pk)
    handlers = {"approve": officials.approve, "reject": officials.reject, "suspend": officials.suspend, "reinstate": officials.reinstate}
    if action not in handlers:
        return redirect("gova_pp:officials")
    handlers[action](official, request.user, request.POST.get("note", "").strip())
    done = {"approve": "approved", "reject": "turned down", "suspend": "suspended", "reinstate": "reinstated"}[action]
    messages.success(request, f"{official.full_name} {done}.")
    return redirect("gova_pp:officials")


@superuser_required
@require_POST
def invite_create(request):
    GovernmentInvite.objects.create(
        name=request.POST.get("name", "").strip()[:120], institution=request.POST.get("institution", "").strip()[:160],
        region=request.POST.get("region", ""), created_by=request.user, expires_at=timezone.now() + timedelta(days=INVITE_DAYS),
    )
    messages.success(request, "Invite link created. Copy it and send it to the officer.")
    return redirect("gova_pp:officials")


@superuser_required
@require_POST
def invite_revoke(request, pk):
    get_object_or_404(GovernmentInvite, pk=pk, used_at__isnull=True).delete()
    return redirect("gova_pp:officials")

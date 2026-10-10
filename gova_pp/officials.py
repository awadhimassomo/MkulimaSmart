"""Decisions on government officers: who may use the government dashboard (see access.has_government_access)."""
from django.utils import timezone

from .models import GovernmentOfficial


def _decide(official, status, by, note=""):
    official.status = status
    official.decided_by = by
    official.decided_at = timezone.now()
    official.decision_note = (note or "")[:255]
    official.save()


def approve(official, by, note=""):
    _decide(official, GovernmentOfficial.APPROVED, by, note)


def reject(official, by, note=""):
    _decide(official, GovernmentOfficial.REJECTED, by, note)


def suspend(official, by, note=""):
    _decide(official, GovernmentOfficial.SUSPENDED, by, note)


def reinstate(official, by, note=""):
    approve(official, by, note)


def convert_staff(user, by):
    """
    Move an existing staff account onto the officer role: it keeps the government dashboard but stops being
    `is_staff`, so it can no longer open the Django admin or other staff-only pages. Superusers are left alone.
    """
    if user.is_superuser:
        raise ValueError("Administrators keep their access.")
    first = (user.first_name or "").strip()
    name = f"{first} {user.last_name or ''}".strip() or user.email or str(user.pk)
    official, _ = GovernmentOfficial.objects.get_or_create(
        user=user, defaults={"full_name": name, "institution": "Government", "via": "existing"},
    )
    _decide(official, GovernmentOfficial.APPROVED, by, "Moved from a staff account.")
    if user.is_staff:
        user.is_staff = False
        user.save(update_fields=["is_staff"])
    return official

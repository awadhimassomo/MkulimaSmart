"""Decisions on government officers: who may use the government dashboard (`is_staff`) and who may not."""
from django.utils import timezone

from .models import GovernmentOfficial


def _grant(official):
    user = official.user
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        official.staff_granted = True


def _revoke(official):
    user = official.user
    if official.staff_granted and user.is_staff and not user.is_superuser:
        user.is_staff = False
        user.save(update_fields=["is_staff"])


def _decide(official, status, by, note=""):
    official.status = status
    official.decided_by = by
    official.decided_at = timezone.now()
    official.decision_note = (note or "")[:255]


def approve(official, by, note=""):
    _grant(official)
    _decide(official, GovernmentOfficial.APPROVED, by, note)
    official.save()


def reject(official, by, note=""):
    _revoke(official)
    _decide(official, GovernmentOfficial.REJECTED, by, note)
    official.save()


def suspend(official, by, note=""):
    _revoke(official)
    _decide(official, GovernmentOfficial.SUSPENDED, by, note)
    official.save()


def reinstate(official, by, note=""):
    approve(official, by, note)

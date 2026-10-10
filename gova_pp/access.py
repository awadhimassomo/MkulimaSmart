"""Who may use the government dashboard and answer farmers' messages."""


def has_government_access(user):
    """
    Superusers, accounts that were already staff before officers had their own role, and approved
    GovernmentOfficial records. Approval no longer makes anyone `is_staff`, so officers cannot open
    the Django admin or the other staff-only pages.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if user.is_superuser or user.is_staff:
        return True
    from .models import GovernmentOfficial

    return GovernmentOfficial.objects.filter(user=user, status=GovernmentOfficial.APPROVED).exists()

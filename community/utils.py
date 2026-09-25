"""Helpers for showing Farmer Talk discussions on other apps' pages (product pages, catalog pages)."""
from django.db.models import Q

from .models import Discussion


def discussions_for_names(*names, limit=5):
    """
    Active discussions whose crop or seed_variety matches any of the given names
    (case-insensitive, either direction: "Maize" matches a product called "Maize Seed 2kg",
    and "Zamseed 606 Maize" matches a discussion tagged just "Maize").
    """
    names = [n.strip() for n in names if n and n.strip()]
    if not names:
        return Discussion.objects.none()

    query = Q()
    for name in names:
        # Whole-string containment catches short names inside a longer field
        # (e.g. crop="Maize Grain" contains name="Maize").
        query |= Q(crop__icontains=name) | Q(seed_variety__icontains=name)
        # Word-level containment the other way round: name is often a longer product
        # title ("Zamseed 606 (2kg packet)") that contains a discussion's shorter
        # crop or seed_variety words ("Zamseed", "606", "Maize").
        for word in [w for w in name.split() if len(w) > 2]:
            query |= Q(crop__iexact=word) | Q(seed_variety__icontains=word)

    return Discussion.objects.filter(query, is_active=True).select_related("author").distinct()[:limit]

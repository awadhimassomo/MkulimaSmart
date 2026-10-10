from django import template

register = template.Library()


@register.simple_tag
def ops_badges():
    """Small counters for the navigation: things waiting on an administrator."""
    from gova_pp.models import GovernmentOfficial
    from kikapu_bridge.models import ReplyDelivery

    return {
        "officials": GovernmentOfficial.objects.filter(status=GovernmentOfficial.PENDING).count(),
        "deliveries": ReplyDelivery.objects.filter(delivered_at__isnull=True, gave_up=True).count(),
    }

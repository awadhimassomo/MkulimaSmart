from django import template
from django.db.models.query import QuerySet
from django.db.models import Sum
from website.models import CartItem

register = template.Library()

@register.filter
def primary_image(images):
    """
    Returns the first primary image from a product's images
    Usage: {{ product.images|primary_image }}
    """
    if not images:
        return None
    
    # Try to find a primary image
    primary = images.filter(is_primary=True).first()
    if primary:
        return primary
    
    # If no primary image is found, return the first image
    return images.first()


@register.simple_tag(takes_context=True)
def cart_count(context):
    """
    Safe cart item count (quantity sum) for the current user; returns 0 for anonymous or missing carts.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return 0
    qty = (
        CartItem.objects.filter(cart__user=user)
        .aggregate(total=Sum("quantity"))
        .get("total")
    )
    return qty or 0

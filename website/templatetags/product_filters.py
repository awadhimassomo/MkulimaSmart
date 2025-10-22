from django import template
from django.db.models.query import QuerySet

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

from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """{{ dict|get_item:key }} — dictionary lookup with a variable key."""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""

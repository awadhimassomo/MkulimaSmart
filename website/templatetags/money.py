from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def tzs(value):
    """
    A price for display: whole shillings with thousands separators (18000.00 -> 18,000), keeping two decimals only when
    there really are cents (18000.50 -> 18,000.50). Anything that is not a number is returned unchanged.
    """
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    if amount == amount.to_integral_value():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"

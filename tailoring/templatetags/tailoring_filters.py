"""
Custom template filters for the tailoring app.
"""
from django import template

register = template.Library()


@register.filter(name='format_number')
def format_number(value):
    """
    Format a number with commas for thousands separators.
    Example: 1234567 -> 1,234,567
    """
    try:
        value = int(value)
        return f"{value:,}"
    except (ValueError, TypeError):
        return value

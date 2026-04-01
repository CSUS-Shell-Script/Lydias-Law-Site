from django import template
import re

register = template.Library()

@register.filter
def format_phone(value):
    if not value:
        return "--"

    digits = re.sub(r"\D", "", str(value))

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]} - {digits[6:]}"
    
    return value
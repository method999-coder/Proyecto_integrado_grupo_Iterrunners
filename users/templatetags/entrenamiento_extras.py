from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter(needs_autoescape=True)
def highlight_plus(value, autoescape=True):
    if value is None:
        return ""

    text = conditional_escape(value) if autoescape else str(value)
    rendered = str(text)
    rendered = rendered.replace("+", '<span class="plus-mark">+</span>')
    rendered = rendered.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return mark_safe(rendered)

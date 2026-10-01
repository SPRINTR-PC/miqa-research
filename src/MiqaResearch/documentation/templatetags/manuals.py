from django import template

from documentation.manuals import MANUALS

register = template.Library()


@register.simple_tag
def readable_manuals(user):
    """The manuals ``user`` may read, in registry order."""
    return [manual for manual in MANUALS.values() if manual.can_read(user)]

from django import template
from django.utils.html import format_html
from django.utils.translation import gettext

from documentation.help_links import resolve
from documentation.manuals import MANUALS

register = template.Library()


@register.simple_tag
def readable_manuals(user):
    """The manuals ``user`` may read, in registry order."""
    return [manual for manual in MANUALS.values() if manual.can_read(user)]


@register.simple_tag(takes_context=True)
def manual_link(context, manual, label, text=None):
    """A Help Link to a manual section: a "?" button, or an inline link when ``text`` is given.

    Renders nothing for users who can't read the manual.
    """
    link = resolve(context["request"].user, manual, label)
    if link is None:
        return ""
    tooltip = gettext("Help: %(title)s") % {"title": link.title}
    if text:
        return format_html(
            '<a class="help-link-text" href="{}" target="_blank" rel="noopener" title="{}">{}</a>',
            link.url,
            tooltip,
            text,
        )
    return format_html(
        '<a class="help-link" href="{}" target="_blank" rel="noopener" aria-label="{}" title="{}">?</a>',
        link.url,
        tooltip,
        tooltip,
    )

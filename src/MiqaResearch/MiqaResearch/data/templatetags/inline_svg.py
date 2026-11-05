import re

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def svg(icon_name: str, icon_classes: str = None):
    # Find the absolute path to the static file
    absolute_path = finders.find(f"icons/{icon_name.removesuffix('.svg')}.svg")

    if not absolute_path:
        if settings.DEBUG:
            return ""
        return ""

    # Open and read the SVG file
    with open(absolute_path, encoding='utf-8') as file:
        svg_content = file.read()

    # Add the provided classes to the SVG element. If the SVG already has classes, append the icon_classes to the already present classes.
    if icon_classes:
        # Check if the svg already has a class attribute
        class_match = re.search(r'<svg[^>]*\sclass=["\']([^"\']*)["\']', svg_content)
        if class_match:
            existing_classes = class_match.group(1)
            combined_classes = f"{existing_classes} {icon_classes}"
            svg_content = re.sub(
                r'(<svg[^>]*\sclass=["\'])([^"\']*?)(["\'])',
                rf'\g<1>{combined_classes}\g<3>',
                svg_content
            )
        else:
            svg_content = svg_content.replace('<svg', f'<svg class="{icon_classes}"')

    # Mark it safe so Django doesn't escape the HTML tags
    return mark_safe(svg_content)

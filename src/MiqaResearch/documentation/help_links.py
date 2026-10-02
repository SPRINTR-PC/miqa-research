"""Help Links: app pages point at manual sections by stable ``app-<area>-<topic>`` label."""

import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language

from documentation.manuals import MANUALS, SOURCE_LANGUAGE, build_languages, canonical_url_path

logger = logging.getLogger(__name__)


class UnknownHelpLink(LookupError):
    """A Help Link names a manual or label that the English build doesn't have."""


@dataclass(frozen=True)
class HelpLink:
    url: str
    title: str


def _labels(manual, language) -> dict | None:
    path = manual.build_dir(language) / "labels.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(user, manual_slug: str, label: str) -> HelpLink | None:
    """The Help Link for ``user``, or ``None`` when they can't read the manual.

    An unknown manual or label raises in DEBUG; otherwise it is logged and gives ``None``.
    """
    try:
        return _resolve(user, manual_slug, label)
    except UnknownHelpLink:
        if settings.DEBUG:
            raise
        logger.warning("Unknown Help Link %s:%s", manual_slug, label, exc_info=True)
        return None


def _resolve(user, manual_slug, label):
    manual = MANUALS.get(manual_slug)
    if manual is None:
        raise UnknownHelpLink(f"No manual {manual_slug!r}")
    if not manual.can_read(user):
        return None
    # The English build decides which labels exist; pages are language-neutral.
    target = (_labels(manual, SOURCE_LANGUAGE) or {}).get(label)
    if target is None:
        raise UnknownHelpLink(f"No label {label!r} in the English {manual.title} build")
    title = target["title"]
    for language in build_languages(get_language() or SOURCE_LANGUAGE):
        translated = (_labels(manual, language) or {}).get(label)
        if translated is not None:
            title = translated["title"]
            break
    url_path = canonical_url_path(target["page"])
    kwargs = {"manual": manual.slug, "page": url_path} if url_path else {"manual": manual.slug}
    return HelpLink(f"{reverse('manuals:page', kwargs=kwargs)}#{target['anchor']}", title)


def manual_url(request, manual: str, label: str) -> str | None:
    """URL of a manual section by label, or ``None`` when the user can't read that manual."""
    link = resolve(request.user, manual, label)
    return link.url if link else None

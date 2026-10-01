"""The closed registry of in-app manuals and how their built pages are found."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

SOURCE_LANGUAGE = "en"
MANUALS_DIR = Path(__file__).resolve().parent / "manuals"


def _signed_in(user) -> bool:
    return user.is_authenticated


def _superuser_or_staff(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.is_staff)


@dataclass(frozen=True)
class Manual:
    slug: str
    title: str
    source_dir: Path
    can_read: Callable[[object], bool]

    def build_dir(self, language: str) -> Path:
        return Path(settings.MANUALS_BUILD_DIR) / self.slug / language


MANUALS = {
    manual.slug: manual
    for manual in (
        Manual("user", "User Manual", MANUALS_DIR / "user", _signed_in),
        Manual("technical", "Technical Manual", MANUALS_DIR / "technical", _superuser_or_staff),
    )
}


@dataclass(frozen=True)
class Page:
    manual: Manual
    language: str
    data: dict

    @property
    def has_untranslated_parts(self) -> bool:
        """True when served in a translation and Sphinx marked paragraphs as untranslated."""
        return self.language != SOURCE_LANGUAGE and 'class="untranslated"' in self.data["body"]


def load_page(manual: Manual, docname: str, language: str) -> Page | None:
    build_dir = manual.build_dir(language).resolve()
    path = (build_dir / f"{docname}.fjson").resolve()
    if not path.is_relative_to(build_dir) or not path.is_file():
        return None
    return Page(manual, language, json.loads(path.read_text(encoding="utf-8")))


def build_languages(language: str) -> list[str]:
    """Builds to try for an active language, most specific first, always ending in English."""
    candidates = [language.lower(), language.lower().split("-")[0], SOURCE_LANGUAGE]
    return list(dict.fromkeys(candidates))


def docnames_for(url_path: str) -> list[str]:
    """Sphinx docnames a dirhtml-style URL path may name: ``""`` is ``index``, ``a/`` may be ``a/index``."""
    return [f"{url_path}/index", url_path] if url_path else ["index"]


def canonical_url_path(docname: str) -> str:
    """The dirhtml-style URL path Sphinx's JSON links use for a docname."""
    if docname == "index":
        return ""
    return docname.removesuffix("/index")

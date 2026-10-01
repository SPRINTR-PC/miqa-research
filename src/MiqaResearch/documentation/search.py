"""Search a manual's build-time section index (``search.json``)."""

import json
import unicodedata
from dataclasses import dataclass

from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from documentation.manuals import Manual, build_languages, canonical_url_path

MIN_QUERY_LENGTH = 2
SNIPPET_LENGTH = 160
SNIPPET_LEAD = 40


@dataclass(frozen=True)
class Result:
    url: str
    title: str
    breadcrumb: list[str]
    snippet: SafeString


def fold(text: str) -> str:
    """Lower-cased and accent-free, for matching."""
    return _fold_with_offsets(text)[0]


def _fold_with_offsets(text: str) -> tuple[str, list[int]]:
    """``fold(text)`` plus, for each folded character, the index of the character it came from."""
    folded, offsets = [], []
    for index, char in enumerate(text):
        decomposed = unicodedata.normalize("NFKD", char)
        for out in "".join(c for c in decomposed if not unicodedata.combining(c)).casefold():
            folded.append(out)
            offsets.append(index)
    return "".join(folded), offsets


def _hits(text: str, words: list[str]) -> list[tuple[int, int]]:
    """Merged ``(start, end)`` spans of ``text`` where any of the folded ``words`` occur."""
    folded, offsets = _fold_with_offsets(text)
    spans = []
    for word in words:
        start = folded.find(word)
        while start != -1:
            spans.append((offsets[start], offsets[start + len(word) - 1] + 1))
            start = folded.find(word, start + len(word))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def snippet(text: str, words: list[str]) -> SafeString:
    """HTML-escaped text around the first hit, with every hit in ``<mark>``."""
    hits = _hits(text, words)
    start = 0
    if hits and hits[0][0] > SNIPPET_LEAD:
        # Start at a word boundary shortly before the first hit.
        start = text.find(" ", hits[0][0] - SNIPPET_LEAD, hits[0][0]) + 1 or hits[0][0]
    end = min(len(text), start + SNIPPET_LENGTH)
    if end < len(text):
        # End at a word boundary.
        end = max(text.rfind(" ", start + 1, end), 0) or end
    parts, cursor = [], start
    for hit_start, hit_end in hits:
        if hit_end <= start or hit_start >= end:
            continue
        hit_start, hit_end = max(hit_start, start), min(hit_end, end)
        parts += [escape(text[cursor:hit_start]), "<mark>", escape(text[hit_start:hit_end]), "</mark>"]
        cursor = hit_end
    parts.append(escape(text[cursor:end]))
    return mark_safe("…" * (start > 0) + "".join(parts) + "…" * (end < len(text)))


def load_index(manual: Manual, language: str) -> list[dict]:
    """The section index for ``language``'s build, or English's when that language has none."""
    for candidate in build_languages(language):
        path = manual.build_dir(candidate) / "search.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def search(manual: Manual, query: str, language: str) -> list[Result]:
    """Sections containing every word of ``query``; sections with more title hits first."""
    if len(query.strip()) < MIN_QUERY_LENGTH:
        return []
    words = fold(query).split()
    ranked = []
    for entry in load_index(manual, language):
        title = fold(entry["title"])
        haystack = f"{title} {fold(entry['text'])}"
        if all(word in haystack for word in words):
            title_hits = sum(word in title for word in words)
            ranked.append((-title_hits, len(ranked), _result(manual, entry, words)))
    return [result for *_, result in sorted(ranked)]


def _result(manual: Manual, entry: dict, words: list[str]) -> Result:
    url_path = canonical_url_path(entry["page"])
    if url_path:
        page_url = reverse("manuals:page", kwargs={"manual": manual.slug, "page": url_path})
    else:
        page_url = reverse("manuals:page", kwargs={"manual": manual.slug})
    return Result(f"{page_url}#{entry['anchor']}", entry["title"], entry["breadcrumb"], snippet(entry["text"], words))

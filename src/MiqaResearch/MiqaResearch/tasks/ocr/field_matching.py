"""Field-matching stage.

Real Tesseract OCR (Swedish+English) plus #16's label-anchor search: locates
each template field's region by fuzzily matching its label against OCR'd
words, searched across ALL pages of the form -- not a fixed page index, which
is what recovers sample_09's swapped pages with zero special-casing.

Ported from `prototype/issue-16-field-matching`'s pipeline.py/ocr_engine.py/
textnorm.py -- the label-localization + region-carving half only. That
prototype's box-discovery/mark-assignment half measured 13.5-24.2% accuracy
and is deliberately NOT ported here; #48 owns mark detection on the regions
this stage locates.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import cv2
import numpy as np
import pymupdf
import pytesseract
from kpforms.form_schema import FormTemplateSchema

from .preprocessing import pixmap_to_gray

# #16's measured thresholds/margins -- do not re-tune without new data.
MIN_ANCHOR_SCORE = 0.55
CONFIDENT_MARGIN = 0.08
NEIGHBOR_WINDOW = 4
REGION_MIN_HEIGHT = 120

# Value assignment for these types is #48's job (ink-density mark detection);
# this stage only locates their region, it never sets text_value for them.
MARK_FIELD_TYPES = {"checkbox", "radio", "ranged-radio"}

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


@dataclass
class FieldMatch:
    field_id: str
    field_type: str
    page_index: int | None = None
    region: tuple[int, int, int, int] | None = None
    label_match_score: float = 0.0
    text_value: str | None = None
    tesseract_word_confidence: float = 0.0
    # (value, label) pairs for checkbox/radio/ranged-radio fields, in template
    # order -- #48 zips these against the boxes/digits it discovers, so it
    # never needs to re-flatten the template itself.
    options: list[tuple[str, str]] = field(default_factory=list)
    # The label anchor's own bbox (native page coords, same space as `region`).
    # On this form, a mark-type field's option boxes sit level with the
    # label's own (possibly multi-line) span, not below it -- #48 searches
    # this span, not `region` (which is carved for the *next* field's anchor
    # and is the wrong span for these fields; #47's own text_value extraction
    # for non-mark fields still uses `region`, unaffected).
    anchor_bbox: tuple[int, int, int, int] | None = None


@dataclass
class _FlatField:
    id: str
    label: str
    type: str
    order: int
    options: list[tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text normalization (prototype/issue-16-field-matching's textnorm.py)
# ---------------------------------------------------------------------------


def _strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _normalize_text(text: str, strip_diacritics: bool = False) -> str:
    text = text.lower()
    if strip_diacritics:
        text = _strip_diacritics(text)
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _text_similarity(a: str, b: str) -> float:
    """Best of diacritics-preserved and diacritics-stripped SequenceMatcher ratio.

    Swedish å/ä/ö are meaningful letters, not accents to always strip -- but
    Tesseract does sometimes mangle them, so score both ways and keep the better.
    """
    preserved = SequenceMatcher(None, _normalize_text(a), _normalize_text(b)).ratio()
    stripped = SequenceMatcher(None, _normalize_text(a, True), _normalize_text(b, True)).ratio()
    return max(preserved, stripped)


def _tokenize(text: str) -> list[str]:
    return _normalize_text(text).split()


# ---------------------------------------------------------------------------
# Template flattening
# ---------------------------------------------------------------------------


def _field_options(input_field) -> list[tuple[str, str]]:
    if input_field.type in ("checkbox", "radio"):
        return [(o.value, o.label) for o in input_field.options]
    if input_field.type == "ranged-radio":
        return sorted(((o.value, o.label) for o in input_field.optionLabelsAndIndices), key=lambda t: int(t[0]))
    return []


def _flatten_template(template_schema: FormTemplateSchema) -> list[_FlatField]:
    """Document order is the "section/group ordering as a prior" #16 asks for --
    it's literally the order fields appear in the template, which mirrors the
    printed form's order (the template was authored from this form, #12)."""
    fields = []
    order = 0
    for section in template_schema.sections:
        for group in section.inputGroups:
            for input_field in group.fields:
                fields.append(
                    _FlatField(
                        id=input_field.id,
                        label=input_field.label,
                        type=input_field.type,
                        order=order,
                        options=_field_options(input_field),
                    )
                )
                order += 1
    return fields


# ---------------------------------------------------------------------------
# OCR (prototype/issue-16-field-matching's ocr_engine.py, plus deskew/Otsu
# preprocessing per docs/prom-ocr-handoff.md §4[2], which that prototype didn't do)
# ---------------------------------------------------------------------------


def _deskew_angle(gray: np.ndarray) -> float:
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    coords = cv2.findNonZero(binary)
    if coords is None:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle += 90
    return angle


def _preprocess_for_ocr(gray: np.ndarray) -> np.ndarray:
    """Light deskew + Otsu binarization.

    Skew is minimal across every fixture in this sample set (per their
    manifests), so the correction is deliberately conservative: skip rotating
    for a negligible or implausibly large detected angle (the latter reads as
    noise, not real skew) rather than risk a bad correction on a form that's
    already close to straight.
    """
    angle = _deskew_angle(gray)
    if 0.1 <= abs(angle) <= 5.0:
        height, width = gray.shape
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        gray = cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return binary


def _ocr_words(pixmap: pymupdf.Pixmap) -> list[dict]:
    """Word-level Tesseract OCR, grouped into reading order (block/par/line,
    then top, then left within a line)."""
    processed = _preprocess_for_ocr(pixmap_to_gray(pixmap))
    data = pytesseract.image_to_data(processed, lang="swe+eng", config="--psm 6", output_type=pytesseract.Output.DICT)

    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text or not any(c.isalnum() for c in text):
            # Drop punctuation-only tokens -- Tesseract routinely misreads empty
            # printed checkbox squares as things like "[]"/"--"/"|". These
            # normalize to nothing during scoring anyway, but a stray one can
            # still corrupt a matched window's bounding box if kept.
            continue
        try:
            conf = float(data["conf"][i])
        except ValueError:
            conf = -1.0
        left, top, width, height = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(
            {
                "text": text,
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
                "conf": conf,
                "block": data["block_num"][i],
                "par": data["par_num"][i],
                "line": data["line_num"][i],
            }
        )

    lines: dict[tuple, list[dict]] = {}
    for word in words:
        lines.setdefault((word["block"], word["par"], word["line"]), []).append(word)
    ordered_lines = sorted(lines.items(), key=lambda kv: min(w["top"] for w in kv[1]))
    result = []
    for _, line_words in ordered_lines:
        result.extend(sorted(line_words, key=lambda w: w["left"]))
    return result


# ---------------------------------------------------------------------------
# Label-anchor search + region carving (prototype/issue-16-field-matching's pipeline.py)
# ---------------------------------------------------------------------------


def _bbox_of(window: list[dict]) -> tuple[int, int, int, int]:
    return (
        min(w["left"] for w in window),
        min(w["top"] for w in window),
        max(w["right"] for w in window),
        max(w["bottom"] for w in window),
    )


def _best_window_match(label: str, words: list[dict]) -> tuple[float, tuple[int, int, int, int] | None]:
    """Slide fixed-word-count windows over (page- or region-ordered) OCR words."""
    n_tokens = max(1, len(_tokenize(label)))
    best_score, best_bbox = 0.0, None
    for win_len in (n_tokens, max(1, n_tokens - 1), n_tokens + 1):
        for start in range(0, max(0, len(words) - win_len + 1)):
            window = words[start : start + win_len]
            score = _text_similarity(label, " ".join(w["text"] for w in window))
            if score > best_score:
                best_score, best_bbox = score, _bbox_of(window)
    return best_score, best_bbox


def _score_all_pages(label: str, pages_words: list[list[dict]]) -> list[tuple[float, int, tuple | None]]:
    """Best match per page, sorted best-first: [(score, page_idx, bbox), ...]."""
    per_page = []
    for page_idx, words in enumerate(pages_words):
        score, bbox = _best_window_match(label, words)
        per_page.append((score, page_idx, bbox))
    per_page.sort(key=lambda t: t[0], reverse=True)
    return per_page


def _localize_field_anchors(
    fields: list[_FlatField], pages_words: list[list[dict]]
) -> dict[str, tuple[float, int, tuple | None]]:
    """For every field, search all pages independently, then resolve close calls
    using document order as a prior: fields with a clear top-page winner are
    "confident" and vote; an ambiguous field defers to the majority page among
    its nearby confident neighbors (by template order), if one of its own
    candidate pages agrees with that vote closely enough to still be plausible.

    This is what recovers near-duplicate labels across sections (e.g. this
    template's two ~130-char livskvalitet questions differ by one word) and
    what makes page/section assignment survive a physically swapped page order
    (sample_09) with no fixed-index assumption anywhere.
    """
    per_field_pages = {f.id: _score_all_pages(f.label, pages_words) for f in fields}

    confident_page: dict[int, int] = {}
    for f in fields:
        top_score, top_page, _ = per_field_pages[f.id][0]
        second_score = per_field_pages[f.id][1][0] if len(per_field_pages[f.id]) > 1 else 0.0
        if top_score >= MIN_ANCHOR_SCORE and (top_score - second_score) >= CONFIDENT_MARGIN:
            confident_page[f.order] = top_page

    orders = sorted(confident_page)
    anchors: dict[str, tuple[float, int, tuple | None]] = {}
    for f in fields:
        pages = per_field_pages[f.id]
        top_score, top_page, top_bbox = pages[0]
        second_score = pages[1][0] if len(pages) > 1 else 0.0
        is_confident = top_score >= MIN_ANCHOR_SCORE and (top_score - second_score) >= CONFIDENT_MARGIN

        chosen = (top_score, top_page, top_bbox)
        if not is_confident and orders:
            nearby = [confident_page[o] for o in orders if abs(o - f.order) <= NEIGHBOR_WINDOW]
            if nearby:
                vote_page = max(set(nearby), key=nearby.count)
                for score, page_idx, bbox in pages:
                    if page_idx == vote_page and score >= top_score - 0.2:
                        chosen = (score, page_idx, bbox)
                        break

        anchors[f.id] = chosen
    return anchors


def _compute_field_regions(
    fields: list[_FlatField],
    anchors: dict[str, tuple[float, int, tuple | None]],
    page_heights: list[int],
) -> dict[str, tuple[int, int, int]]:
    """Per page, order the fields whose anchor landed there by vertical
    position and carve each one's content region: from this field's anchor
    bottom to the next field's anchor top, full page width. A multi-line-
    wrapped label's own bbox can legitimately overlap the next field's anchor
    (two real spans crossing, not a bug) -- clamp to a minimum region height
    in that case rather than losing the field entirely.
    """
    by_page: dict[int, list[tuple[_FlatField, tuple]]] = {}
    for f in fields:
        score, page_idx, bbox = anchors[f.id]
        if score < MIN_ANCHOR_SCORE or bbox is None:
            continue
        by_page.setdefault(page_idx, []).append((f, bbox))

    regions: dict[str, tuple[int, int, int]] = {}
    for page_idx, items in by_page.items():
        items.sort(key=lambda t: t[1][1])  # top
        for i, (f, bbox) in enumerate(items):
            top = bbox[3]  # bottom edge of this field's own anchor
            bottom = items[i + 1][1][1] if i + 1 < len(items) else page_heights[page_idx]
            if bottom <= top:
                bottom = min(top + REGION_MIN_HEIGHT, page_heights[page_idx])
            regions[f.id] = (page_idx, top, bottom)
    return regions


def _words_in_region(words: list[dict], top: int, bottom: int, slack: int = 6) -> list[dict]:
    return [w for w in words if top - slack <= w["top"] <= bottom + slack]


# A carved region runs all the way to the *next* confidently-anchored field,
# which is the right span for locating a choice field's option sub-anchors
# (#48) but far too wide for a direct text grab: an unrelated field's
# instructional text or this form's footer text ends up swept in as soon as a
# neighboring field doesn't anchor confidently. Non-mark fields' answers sit
# right after their own label, so cap how far below the anchor text extraction
# looks instead of trusting the full carved region.
TEXT_VALUE_MAX_REGION_HEIGHT = 150


def _extract_text_value(region_words: list[dict]) -> tuple[str | None, float]:
    """Non-mark fields (text/numeric/string/datetime) get their classic-path
    value straight from the OCR words in their region -- no mark detection
    needed for these types."""
    if not region_words:
        return None, 0.0
    text = " ".join(w["text"] for w in region_words)
    confidences = [w["conf"] for w in region_words if w["conf"] >= 0]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, mean_confidence


def match_fields(pages: list[pymupdf.Pixmap], template_schema: FormTemplateSchema) -> list[FieldMatch]:
    fields = _flatten_template(template_schema)
    pages_words = [_ocr_words(page) for page in pages]
    page_heights = [page.height for page in pages]
    page_widths = [page.width for page in pages]

    anchors = _localize_field_anchors(fields, pages_words)
    regions = _compute_field_regions(fields, anchors, page_heights)

    matches = []
    for f in fields:
        score, page_idx, anchor_bbox = anchors[f.id]
        region = regions.get(f.id)

        text_value, confidence = None, 0.0
        if region is not None and f.type not in MARK_FIELD_TYPES:
            region_page_idx, top, bottom = region
            bottom = min(bottom, top + TEXT_VALUE_MAX_REGION_HEIGHT)
            text_value, confidence = _extract_text_value(_words_in_region(pages_words[region_page_idx], top, bottom))

        matches.append(
            FieldMatch(
                field_id=f.id,
                field_type=f.type,
                page_index=page_idx,
                region=(0, region[1], page_widths[region[0]], region[2]) if region is not None else None,
                label_match_score=score,
                text_value=text_value,
                tesseract_word_confidence=confidence,
                options=f.options,
                anchor_bbox=anchor_bbox if region is not None else None,
            )
        )
    return matches

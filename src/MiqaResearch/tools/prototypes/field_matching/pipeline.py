"""
PROTOTYPE -- throwaway code for issue #16.

The actual field-matching algorithm: given a sample's rendered+OCR'd pages and the
flattened template, (1) localize each field's label text anywhere on any page
(this, not a hardcoded page index, is what makes section/page assignment survive
sample_09's swapped pages), (2) carve out each field's content region as "from this
field's anchor to the next field's anchor, same page", (3) inside a field's region,
locate its option labels (checkbox/radio) or scale digits (ranged-radio) as
sub-anchors, (4) discover the nearest printed box (or, for circle-scale fields, use
a dilated crop of the digit itself) and run issue #15's ink-density detector on it,
(5) assemble predicted values and confidence signals per field.
"""

import re

from . import geometry, textnorm
from .detector import THRESHOLDS, ink_density_score

# Mutable copy: issue #15's thresholds were tuned on hand-labelled fixed-size
# crops; benchmark.py recalibrates this copy against *this* pipeline's own
# auto-discovered-box crops (see its docstring) after an initial scoring pass.
ACTIVE_THRESHOLDS = dict(THRESHOLDS)

MIN_ANCHOR_SCORE = 0.55
MIN_OPTION_SCORE = 0.5
CONFIDENT_MARGIN = 0.08  # gap between best- and second-best-page score to call a match "confident"
NEIGHBOR_WINDOW = 4  # how many fields before/after (document order) count as "neighbors" for the page prior
_DIGIT_RE = re.compile(r"^\d{1,2}$")
CANONICAL_BOX_SIZE = 38  # px at 200dpi -- matches issue #15's hand-measured box size


def _label_tokens(label):
    return textnorm.tokenize(label)


def _bbox_of(window):
    return {
        "left": min(w["left"] for w in window),
        "top": min(w["top"] for w in window),
        "right": max(w["right"] for w in window),
        "bottom": max(w["bottom"] for w in window),
    }


def _best_window_match(label, words):
    """
    Slide fixed-word-count windows over the OCR word list (already page- or
    region-ordered). Returns (score, bbox) or (0.0, None).

    KNOWN LIMITATION (see README.md "Known failure modes"): on this form,
    checkbox/radio rows often OCR as garbage tokens (Tesseract misreads empty
    printed squares as things like "Od"/"MH"/"DO") that Tesseract itself places on
    the *same* line as the adjacent question text -- so restricting windows to
    single OCR lines does not protect against a label match bleeding into the
    options that follow it (tried, made results worse -- Tesseract's line
    assignment is the thing that's already wrong). A bounding-box-height cap on
    candidate windows was also tried and rejected too many legitimate matches
    (word-level top/bottom jitter, e.g. from diacritics, pushed genuine single-line
    windows over the cap). Short-label radio fields (e.g. "12. Anvander Du...
    bloja?" immediately followed by a "Nej"/"Ja" row) are the main fields this
    still gets wrong -- see README.md for the recommended follow-up.
    """
    n_tokens = max(1, len(_label_tokens(label)))
    best_score, best_bbox = 0.0, None
    for win_len in (n_tokens, max(1, n_tokens - 1), n_tokens + 1):
        for start in range(0, max(0, len(words) - win_len + 1)):
            window = words[start : start + win_len]
            joined = " ".join(w["text"] for w in window)
            score = textnorm.similarity(label, joined)
            if score > best_score:
                best_score = score
                best_bbox = _bbox_of(window)
    return best_score, best_bbox


def _score_all_pages(label, pages_words):
    """Best match per page, sorted best-first: [(score, page_idx, bbox), ...]."""
    per_page = []
    for page_idx, words in enumerate(pages_words):
        score, bbox = _best_window_match(label, words)
        per_page.append((score, page_idx, bbox))
    per_page.sort(key=lambda t: t[0], reverse=True)
    return per_page


def localize_field_anchors(fields, pages_words):
    """
    For every field, search all pages independently first. Some templates repeat
    near-identical label text across sections (e.g. Q15 and Q24 here differ in only
    one word of a ~130-char sentence) -- on noisy OCR, the *wrong* page's real text
    can score as high as the *right* page's OCR-mangled text, so a pure per-field
    best-page pick is unreliable exactly when it matters most. We resolve close
    calls using document order as a prior (the issue's "section/group ordering as
    a prior"): fields with a clear top-page winner are "confident" and vote; an
    ambiguous field defers to the majority page among its nearby confident
    neighbors (by template order), if one of its own candidate pages agrees with
    that vote closely enough to still be plausible.
    """
    per_field_pages = {f.id: _score_all_pages(f.label, pages_words) for f in fields}

    confident_page = {}
    for f in fields:
        pages = per_field_pages[f.id]
        top_score = pages[0][0]
        second_score = pages[1][0] if len(pages) > 1 else 0.0
        if top_score >= MIN_ANCHOR_SCORE and (top_score - second_score) >= CONFIDENT_MARGIN:
            confident_page[f.order] = pages[0][1]

    orders = sorted(confident_page)
    anchors = {}
    for f in fields:
        pages = per_field_pages[f.id]
        top_score, top_page, top_bbox = pages[0]
        second_score = pages[1][0] if len(pages) > 1 else 0.0
        is_confident = top_score >= MIN_ANCHOR_SCORE and (top_score - second_score) >= CONFIDENT_MARGIN

        chosen_score, chosen_page, chosen_bbox = top_score, top_page, top_bbox
        if not is_confident and orders:
            nearby = [confident_page[o] for o in orders if abs(o - f.order) <= NEIGHBOR_WINDOW]
            if nearby:
                vote_page = max(set(nearby), key=nearby.count)
                for score, page_idx, bbox in pages:
                    if page_idx == vote_page and score >= top_score - 0.2:
                        chosen_score, chosen_page, chosen_bbox = score, page_idx, bbox
                        break

        anchors[f.id] = {"score": chosen_score, "page": chosen_page, "bbox": chosen_bbox}
    return anchors


REGION_MIN_HEIGHT = 120  # px fallback when the next field's anchor overlaps this one's (see below)


def compute_field_regions(fields, anchors, page_heights):
    """
    Per page, order the fields whose anchor landed there by vertical position and
    carve each one's content region: (page, y_top, y_bottom) spanning full page
    width, from this field's anchor bottom to the next field's anchor top.

    A multi-line-wrapped label (its own anchor bbox spans two OCR lines) can end
    up with a bottom edge past where the *next* field's anchor starts -- an
    overlap, not a bug in either anchor individually, just two real spans that
    cross. Left alone this produces an inverted (top > bottom) region that matches
    zero words, silently losing all of that field's options. Clamp to a minimum
    region height in that case rather than giving up on the field entirely.
    """
    by_page = {}
    for f in fields:
        a = anchors[f.id]
        if a["score"] < MIN_ANCHOR_SCORE or a["bbox"] is None:
            continue
        by_page.setdefault(a["page"], []).append((f, a["bbox"]))

    regions = {}
    for page_idx, items in by_page.items():
        items.sort(key=lambda t: t[1]["top"])
        for i, (f, bbox) in enumerate(items):
            top = bbox["bottom"]
            bottom = items[i + 1][1]["top"] if i + 1 < len(items) else page_heights[page_idx]
            if bottom <= top:
                bottom = min(top + REGION_MIN_HEIGHT, page_heights[page_idx])
            regions[f.id] = (page_idx, top, bottom)
    return regions


def _words_in_region(words, top, bottom, slack=6):
    return [w for w in words if top - slack <= w["top"] <= bottom + slack]


def _ranged_radio_group(field):
    return "ranged-radio-grid" if len(field.options) > 6 else "circle-scale"


def match_box_mark_field(field, region_words, page_gray, page_boxes):
    """
    Returns (predicted_values: list[str], signals: dict). Handles checkbox, radio,
    and ranged-radio uniformly by first localizing each option's sub-anchor, then
    discovering/scoring its candidate box.
    """
    expected = len(field.options)
    found_anchors = 0
    marks = []  # list of (value, score: float, group: str)

    if field.type == "ranged-radio":
        group = _ranged_radio_group(field)
        threshold_group = group
        expected_values = {int(v) for v, _ in field.options}
        digit_words = [w for w in region_words if _DIGIT_RE.match(w["text"]) and int(w["text"]) in expected_values]
        digit_words.sort(key=lambda w: w["left"])
        options_sorted = sorted(field.options, key=lambda t: int(t[0]))
        for (value, _label), word in zip(options_sorted, digit_words):
            found_anchors += 1
            if group == "ranged-radio-grid":
                box = geometry.find_option_box(word, page_boxes)
                crop = (
                    geometry.crop_centered(page_gray, box, CANONICAL_BOX_SIZE)
                    if box
                    else geometry.crop(page_gray, (word["left"], word["top"] - 45, word["width"], 38), pad=2)
                )
            else:
                crop = geometry.crop(
                    page_gray, (word["left"], word["top"], word["width"], word["height"]), pad=18
                )
            score = ink_density_score(crop)
            marks.append((value, score, threshold_group))
    else:
        threshold_group = field.type  # "checkbox" or "radio"
        for value, label_text in field.options:
            score, bbox = _best_window_match(label_text, region_words)
            if score < MIN_OPTION_SCORE or bbox is None:
                continue
            found_anchors += 1
            box = geometry.find_option_box(bbox, page_boxes)
            if box is None:
                marks.append((value, 0.0, threshold_group))
                continue
            crop = geometry.crop_centered(page_gray, box, CANONICAL_BOX_SIZE)
            mark_score = ink_density_score(crop)
            marks.append((value, mark_score, threshold_group))

    predicted = [v for v, score, group in marks if score >= ACTIVE_THRESHOLDS[group]]
    signals = {
        "option_count_expected": expected,
        "option_count_localized": found_anchors,
        "option_localization_rate": (found_anchors / expected) if expected else 1.0,
        "multi_mark_ambiguous": len(predicted) > 1 and field.type in ("radio", "ranged-radio"),
        "zero_marks_found": len(predicted) == 0,
        "option_scores": [(v, round(s, 4), g) for v, s, g in marks],
    }
    return predicted, signals


def escalate(field, anchor, signals):
    if anchor["score"] < MIN_ANCHOR_SCORE or anchor["bbox"] is None:
        return True
    if field.type in ("checkbox", "radio", "ranged-radio"):
        if signals["option_localization_rate"] < 0.7:
            return True
        if signals["multi_mark_ambiguous"]:
            return True
        expected = signals["option_count_expected"]
        if expected > 2 and abs(signals["option_count_localized"] - expected) > max(1, expected * 0.2):
            return True
    return False


def run_pipeline(fields, pages_words, pages_gray, pages_boxes):
    page_heights = [g.shape[0] for g in pages_gray]
    anchors = localize_field_anchors(fields, pages_words)
    regions = compute_field_regions(fields, anchors, page_heights)

    results = {}
    for f in fields:
        anchor = anchors[f.id]
        record = {
            "field_id": f.id,
            "type": f.type,
            "label_match_score": anchor["score"],
            "anchor_found": anchor["score"] >= MIN_ANCHOR_SCORE,
            "page": anchor["page"],
            "predicted": None,
            "signals": {},
        }
        if f.type in ("checkbox", "radio", "ranged-radio") and f.id in regions:
            page_idx, top, bottom = regions[f.id]
            region_words = _words_in_region(pages_words[page_idx], top, bottom)
            predicted, signals = match_box_mark_field(f, region_words, pages_gray[page_idx], pages_boxes[page_idx])
            record["predicted"] = predicted
            record["signals"] = signals
        record["escalate"] = escalate(f, anchor, record["signals"])
        results[f.id] = record
    return results

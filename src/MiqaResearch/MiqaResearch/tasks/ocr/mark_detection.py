"""Mark-detection stage.

#15's ink-density thresholding on choice-type fields (checkbox / radio /
ranged-radio grid / circle-scale), applied to the regions field_matching (#47)
locates. Box/digit discovery ported from `prototype/issue-16-field-matching`'s
geometry.py; scoring ported from that prototype's detector.py (itself a
reimplementation of #15's winning detector, since #15's own branch was never
merged).

Simplified relative to that prototype in one deliberate way: rather than
re-running OCR to locate each option's own label/digit as a sub-anchor (which
would mean OCR-ing every page twice -- field_matching already did it once),
checkbox/radio/ranged-radio-grid candidates are found by pure OpenCV box
discovery within the field's region, sorted into reading order, and zipped
positionally against the template's option order. This trades some accuracy
on noisy regions for not doubling the classic path's OCR cost; circle-scale
fields still need a small, region-scoped OCR pass since they have no printed
box at all (the digit itself, per #16, is the candidate).

Pixel-size constants below were calibrated at 200dpi (#15/#16's prototypes);
this pipeline renders at 300dpi (#44), so every one is rescaled by 1.5x. The
density THRESHOLDS are dimensionless ratios and are kept verbatim -- per the
ticket, do not re-tune without new data.
"""

import re
from dataclasses import dataclass

import cv2
import numpy as np
import pymupdf
import pytesseract

from .field_matching import MARK_FIELD_TYPES, FieldMatch
from .preprocessing import pixmap_to_gray

THRESHOLDS = {
    "ranged-radio-grid": 0.2682,
    "checkbox": 0.2790,
    "radio": 0.2794,
    "circle-scale": 0.1095,
}

_DPI_SCALE = 300 / 200  # #15/#16 calibrated at 200dpi; this pipeline renders at 300dpi (#44)

BOX_SIDE_RANGE = (round(24 * _DPI_SCALE), round(48 * _DPI_SCALE))
BOX_ASPECT_TOLERANCE = 0.25  # dimensionless -- |w/h - 1|, no DPI rescaling needed
CANONICAL_BOX_SIZE = round(38 * _DPI_SCALE)
INK_DENSITY_BORDER_TRIM = round(6 * _DPI_SCALE)
CIRCLE_DIGIT_PAD = round(18 * _DPI_SCALE)

# checkbox/radio option lists on this form can wrap across multiple lines
# (long option text) well past their label's own anchor span -- not measured
# by #15/#16 (their prototype used hand-given or single-row candidates), so
# not DPI-rescaled from an existing constant; picked empirically against the
# real fixture set (docs/prom-ocr-handoff.md's normal caveat about unmeasured
# thresholds applies here too).
CHECKBOX_MIN_WINDOW_HEIGHT = 350

# A4 at 300dpi (210mm x 297mm). Normalizes away scan-to-scan margin/crop
# variance -- #15 found phone-scan crop margins vary sample-to-sample even
# though rotational skew doesn't -- before applying any pixel-based threshold.
CANONICAL_PAGE_SIZE = (2481, 3508)

# A single candidate has nothing to "clear a margin over"; treat it as
# maximally confident rather than dividing by zero.
_MAX_MARGIN_RATIO = 1_000_000.0

_DIGIT_RE = re.compile(r"^\d{1,2}$")


@dataclass
class MarkResult:
    field_id: str
    value: str | list[str] | None = None
    option_localization: float = 0.0
    mark_margin_ratio: float = 0.0


def _group_for(field_type: str, option_count: int) -> str:
    if field_type == "ranged-radio":
        return "ranged-radio-grid" if option_count > 6 else "circle-scale"
    return field_type  # "checkbox" or "radio"


# ---------------------------------------------------------------------------
# Page normalization (docs/prom-ocr-handoff.md §4[4])
# ---------------------------------------------------------------------------


def _normalize_page(gray: np.ndarray) -> tuple[np.ndarray, float]:
    height, _width = gray.shape
    target_width, target_height = CANONICAL_PAGE_SIZE
    scale_y = target_height / height
    normalized = cv2.resize(gray, (target_width, target_height), interpolation=cv2.INTER_AREA)
    return normalized, scale_y


# ---------------------------------------------------------------------------
# Box/digit discovery (prototype/issue-16-field-matching's geometry.py)
# ---------------------------------------------------------------------------


def _find_square_boxes(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Printed checkbox/radio/grid-digit box outlines via OpenCV contour
    detection -- marked or not, a thin outline and an X-marked box have
    near-identical outer-contour size, so this only answers *where* a box is;
    scoring (below) decides marked vs unmarked."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lo, hi = BOX_SIDE_RANGE
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (lo <= w <= hi and lo <= h <= hi):
            continue
        if abs(w / h - 1.0) > BOX_ASPECT_TOLERANCE:
            continue
        boxes.append((x, y, w, h))
    return boxes


def _find_digit_words(gray: np.ndarray) -> list[dict]:
    """circle-scale fields have no printed box -- the printed digit itself
    (Tesseract reads these reliably; they're machine-printed, not handwritten)
    is the candidate, per #16."""
    data = pytesseract.image_to_data(gray, config="--psm 6", output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not _DIGIT_RE.match(text):
            continue
        words.append(
            {
                "text": text,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            }
        )
    return words


# ---------------------------------------------------------------------------
# Scoring (prototype/issue-15-checkbox-detection's detector.py, reimplemented
# in prototype/issue-16-field-matching's detector.py since #15's own branch
# was never merged)
# ---------------------------------------------------------------------------


def _crop(gray: np.ndarray, rect: tuple[int, int, int, int], pad: int = 0) -> np.ndarray:
    x, y, w, h = rect
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(gray.shape[1], x + w + pad), min(gray.shape[0], y + h + pad)
    return gray[y0:y1, x0:x1]


def _crop_centered(gray: np.ndarray, rect: tuple[int, int, int, int], size: int) -> np.ndarray:
    """A fixed-size crop centered on `rect`'s center, instead of `rect`'s own
    (variable) bounding box -- a heavy mark's ink bleeding past the printed
    outline inflates the raw contour size and dilutes density scoring
    otherwise (#16's finding)."""
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    half = size / 2
    x0, y0 = max(0, int(cx - half)), max(0, int(cy - half))
    x1, y1 = min(gray.shape[1], int(cx + half)), min(gray.shape[0], int(cy + half))
    return gray[y0:y1, x0:x1]


def _ink_density_score(crop_gray: np.ndarray) -> float:
    if crop_gray.size == 0:
        return 0.0
    _, binary = cv2.threshold(crop_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    height, width = binary.shape
    trim = min(INK_DENSITY_BORDER_TRIM, height // 3, width // 3)
    inner = binary[trim : height - trim, trim : width - trim]
    if inner.size == 0:
        return 0.0
    return float(np.count_nonzero(inner)) / inner.size


def _score_box_candidates(
    region_gray: np.ndarray, options: list[tuple[str, str]], group: str
) -> list[tuple[str, float]]:
    boxes = _find_square_boxes(region_gray)
    # ranged-radio-grid: a horizontal 0..10 row, ordered left-to-right by value.
    # checkbox/radio: a reading-order option list (top-to-bottom, then
    # left-to-right within a row -- some rows here hold 2+ options side by
    # side), matching template/document order (#12's template-authored-from-
    # the-form order).
    boxes.sort(key=(lambda b: b[0]) if group == "ranged-radio-grid" else (lambda b: (b[1], b[0])))
    return [
        (value, _ink_density_score(_crop_centered(region_gray, box, CANONICAL_BOX_SIZE)))
        for (value, _label), box in zip(options, boxes[: len(options)])
    ]


def _score_digit_candidates(region_gray: np.ndarray, options: list[tuple[str, str]]) -> list[tuple[str, float]]:
    expected_values = {int(value) for value, _label in options}
    words = [w for w in _find_digit_words(region_gray) if int(w["text"]) in expected_values]
    words.sort(key=lambda w: w["left"])
    options_sorted = sorted(options, key=lambda t: int(t[0]))
    return [
        (
            value,
            _ink_density_score(
                _crop(region_gray, (word["left"], word["top"], word["width"], word["height"]), pad=CIRCLE_DIGIT_PAD)
            ),
        )
        for (value, _label), word in zip(options_sorted, words[: len(options)])
    ]


def _assemble_value(scored: list[tuple[str, float]], threshold: float) -> str | list[str] | None:
    predicted = [value for value, score in scored if score >= threshold]
    if not predicted:
        return None
    if len(predicted) == 1:
        return predicted[0]
    return predicted


def _margin_ratio(scored: list[tuple[str, float]]) -> float:
    scores = sorted((score for _value, score in scored), reverse=True)
    if not scores:
        return 0.0
    if len(scores) == 1 or scores[1] <= 0:
        return _MAX_MARGIN_RATIO if scores[0] > 0 else 0.0
    return scores[0] / scores[1]


def detect_marks(pages: list[pymupdf.Pixmap], field_matches: list[FieldMatch]) -> dict[str, MarkResult]:
    normalized_pages: dict[int, tuple[np.ndarray, float]] = {}

    def normalized_page(page_index: int) -> tuple[np.ndarray, float]:
        if page_index not in normalized_pages:
            normalized_pages[page_index] = _normalize_page(pixmap_to_gray(pages[page_index]))
        return normalized_pages[page_index]

    results = {}
    for match in field_matches:
        if match.field_type not in MARK_FIELD_TYPES or match.anchor_bbox is None:
            continue

        group = _group_for(match.field_type, len(match.options))
        page_gray, scale_y = normalized_page(match.page_index)
        # Search from the label anchor's own top, not field_matching's carved
        # `region` (that's carved for the *next* field's anchor -- the wrong
        # span here, since this form's option boxes sit level with the label
        # itself, not below it). Still search the full page width: the boxes
        # are far to the right of the label's own (narrow) text.
        _anchor_left, anchor_top, _anchor_right, anchor_bottom = match.anchor_bbox
        top = int(anchor_top * scale_y)
        if group in ("ranged-radio-grid", "circle-scale"):
            # A compact single row, level with the anchor -- its own span is enough.
            bottom = int(anchor_bottom * scale_y)
        else:
            # checkbox/radio options can wrap across multiple lines well past
            # the anchor's own bottom edge; guarantee a minimum search height
            # rather than trusting the anchor span or the (sometimes-too-short,
            # #47's own fallback-prone) carved region alone.
            bottom = max(int(anchor_bottom * scale_y), top + CHECKBOX_MIN_WINDOW_HEIGHT)
        bottom = min(bottom, page_gray.shape[0])
        region_gray = page_gray[top:bottom, :]

        if group == "circle-scale":
            scored = _score_digit_candidates(region_gray, match.options)
        else:
            scored = _score_box_candidates(region_gray, match.options, group)

        expected = len(match.options)
        results[match.field_id] = MarkResult(
            field_id=match.field_id,
            value=_assemble_value(scored, THRESHOLDS[group]),
            option_localization=(len(scored) / expected) if expected else 1.0,
            mark_margin_ratio=_margin_ratio(scored),
        )
    return results

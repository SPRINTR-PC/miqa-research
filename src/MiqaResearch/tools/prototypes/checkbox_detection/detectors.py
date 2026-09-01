"""
PROTOTYPE — throwaway code for issue #15.

Three candidate approaches for deciding "is this candidate box marked?" given a
grayscale crop containing (approximately) one checkbox/radio square or one
circle-scale digit cell. Each returns a float score; `benchmark.py` thresholds it.
"""

import cv2
import numpy as np
import pytesseract


def _binarize(crop_gray):
    """Otsu threshold, inverted so ink/marks are foreground (255)."""
    _, bw = cv2.threshold(crop_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def ink_density_score(crop_gray, border_trim=6):
    """
    Fraction of foreground (dark) pixels inside the box, after trimming a border
    margin so the printed box outline itself doesn't count as "ink".
    """
    bw = _binarize(crop_gray)
    h, w = bw.shape
    t = min(border_trim, h // 3, w // 3)
    inner = bw[t : h - t, t : w - t]
    if inner.size == 0:
        return 0.0
    return float(np.count_nonzero(inner)) / inner.size


def contour_morphology_score(crop_gray, border_trim=6):
    """
    Binarize, trim the border (drop the printed box outline / circle), run a
    morphological close to bridge broken pen strokes, then score by the largest
    interior contour's area as a fraction of the interior area. A clean printed
    box outline leaves ~0 interior contour area; an X/tick/fill/circle leaves a
    large one.
    """
    bw = _binarize(crop_gray)
    h, w = bw.shape
    t = min(border_trim, h // 3, w // 3)
    inner = bw[t : h - t, t : w - t]
    if inner.size == 0:
        return 0.0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closed = cv2.morphologyEx(inner, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    largest = max(cv2.contourArea(c) for c in contours)
    return float(largest) / inner.size


def tesseract_ink_score(crop_gray, border_trim=4):
    """
    Ask Tesseract for the interior region's ink bounding boxes via
    image_to_boxes (works on raw glyph shapes, doesn't require recognizable
    text). Score = total boxed-glyph area as a fraction of interior area.
    Falls back to 0 on any Tesseract error (e.g. an empty crop).
    """
    bw = _binarize(crop_gray)
    h, w = bw.shape
    t = min(border_trim, h // 3, w // 3)
    inner = bw[t : h - t, t : w - t]
    if inner.size == 0:
        return 0.0
    # Tesseract expects dark text on light background.
    inv = cv2.bitwise_not(inner)
    try:
        data = pytesseract.image_to_boxes(inv, config="--psm 10")
    except pytesseract.TesseractError:
        return 0.0
    if not data.strip():
        return 0.0
    ih, iw = inner.shape
    total_area = 0.0
    for line in data.strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        _, x1, y1, x2, y2 = parts[:5]
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        total_area += max(0, x2 - x1) * max(0, y2 - y1)
    return min(1.0, total_area / (iw * ih))


DETECTORS = {
    "ink_density": ink_density_score,
    "contour_morphology": contour_morphology_score,
    "tesseract_ink": tesseract_ink_score,
}

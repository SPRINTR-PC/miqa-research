"""
PROTOTYPE -- throwaway code for issue #16.

Box discovery: find printed checkbox/radio square outlines on a page via OpenCV
contour detection (no template geometry needed -- these are found from the scan
itself), then associate each discovered box with the nearest field/option-label
anchor. Calibrated visually against sample_01 (see README.md): printed boxes are
roughly 30-45px square at 200dpi.
"""

import cv2
import numpy as np

BOX_SIDE_RANGE = (24, 48)
BOX_ASPECT_TOLERANCE = 0.25  # |w/h - 1| must be within this


def find_square_boxes(gray_img):
    """
    Returns a list of (x, y, w, h) for contours that look like printed box outlines,
    marked or not -- this is pure size/aspect filtering on outer contours
    (RETR_EXTERNAL), not a "hollow vs filled" shape test: a thin box outline and an
    X-marked or scribbled-full box both end up with an outer contour that encloses
    nearly their full bounding-box area, so contour-fill-fraction can't tell them
    apart at this stage. That's fine -- this function only needs to find *where*
    boxes are; issue #15's ink-density detector (run downstream on the crop) is
    what decides marked vs unmarked.
    """
    _, bw = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    lo, hi = BOX_SIDE_RANGE
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if not (lo <= w <= hi and lo <= h <= hi):
            continue
        if abs(w / h - 1.0) > BOX_ASPECT_TOLERANCE:
            continue
        boxes.append((x, y, w, h))
    return boxes


def nearest_box_above(anchor, boxes, max_dx=26, max_dy_range=(8, 90)):
    """Find the box whose center is roughly above the anchor (ranged-radio grid: box above digit)."""
    ax = (anchor["left"] + anchor["right"]) / 2
    ay = anchor["top"]
    best, best_d = None, None
    for x, y, w, h in boxes:
        bx, by = x + w / 2, y + h / 2
        dx = abs(bx - ax)
        dy = ay - by  # positive if box is above anchor
        if dx > max_dx or not (max_dy_range[0] <= dy <= max_dy_range[1]):
            continue
        d = dx + dy
        if best is None or d < best_d:
            best, best_d = (x, y, w, h), d
    return best


def nearest_box_left(anchor, boxes, max_dy=16, max_dx_range=(8, 140)):
    """Find the box whose center is roughly left of the anchor (checkbox/radio: box left of label)."""
    ax = anchor["left"]
    ay = (anchor["top"] + anchor["bottom"]) / 2
    best, best_d = None, None
    for x, y, w, h in boxes:
        bx, by = x + w / 2, y + h / 2
        dy = abs(by - ay)
        dx = ax - bx  # positive if box is left of anchor
        if dy > max_dy or not (max_dx_range[0] <= dx <= max_dx_range[1]):
            continue
        d = dx + dy
        if best is None or d < best_d:
            best, best_d = (x, y, w, h), d
    return best


def nearest_box_any_direction(anchor, boxes, radius=70):
    """Fallback: nearest box by plain center distance, either direction."""
    ax = (anchor["left"] + anchor["right"]) / 2
    ay = (anchor["top"] + anchor["bottom"]) / 2
    best, best_d = None, None
    for x, y, w, h in boxes:
        bx, by = x + w / 2, y + h / 2
        d = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if d > radius:
            continue
        if best is None or d < best_d:
            best, best_d = (x, y, w, h), d
    return best


def find_option_box(anchor, boxes):
    """
    Unified box-search rule: try "directly above" first (ranged-radio grid layout),
    then "directly left" (checkbox/radio layout), then a small-radius fallback.
    Returns (x, y, w, h) or None.
    """
    return (
        nearest_box_above(anchor, boxes)
        or nearest_box_left(anchor, boxes)
        or nearest_box_any_direction(anchor, boxes)
    )


def crop(gray_img, rect, pad=0):
    x, y, w, h = rect
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(gray_img.shape[1], x + w + pad), min(gray_img.shape[0], y + h + pad)
    return gray_img[y0:y1, x0:x1]


def crop_centered(gray_img, rect, size):
    """
    Crop a FIXED `size`x`size` window centered on `rect`'s center, instead of
    `rect`'s own (variable) bounding box. A discovered box's contour bounding rect
    grows when a mark's ink bleeds past the printed outline (a heavy X often does),
    which dilutes ink-density scoring versus issue #15's fixed-size hand-labelled
    boxes -- re-centering on a canonical size avoids that dilution.
    """
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    half = size / 2
    x0, y0 = max(0, int(cx - half)), max(0, int(cy - half))
    x1, y1 = min(gray_img.shape[1], int(cx + half)), min(gray_img.shape[0], int(cy + half))
    return gray_img[y0:y1, x0:x1]

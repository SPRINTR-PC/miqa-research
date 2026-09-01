"""
PROTOTYPE -- throwaway code for issue #16, reusing issue #15's winning detector
and per-field-type-class thresholds verbatim (see #15: prototype/issue-15-checkbox-
detection, tools/prototypes/checkbox_detection/detectors.py + results.md). #15
answered "is this candidate box marked, given its coordinates"; #16 answers
"where is the candidate box in the first place" -- this module is the boundary
between the two.
"""

import cv2
import numpy as np

THRESHOLDS = {
    "ranged-radio-grid": 0.2682,  # Q1-10 printed-square digit grid
    "checkbox": 0.2790,
    "radio": 0.2794,
    "circle-scale": 0.1095,  # Q17-23 circled-digit marks
}


def _binarize(crop_gray):
    _, bw = cv2.threshold(crop_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def ink_density_score(crop_gray, border_trim=6):
    if crop_gray.size == 0:
        return 0.0
    bw = _binarize(crop_gray)
    h, w = bw.shape
    t = min(border_trim, h // 3, w // 3)
    inner = bw[t : h - t, t : w - t]
    if inner.size == 0:
        return 0.0
    return float(np.count_nonzero(inner)) / inner.size


def is_marked(crop_gray, group):
    return ink_density_score(crop_gray) >= THRESHOLDS[group]

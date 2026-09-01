# Checkbox/radio detection benchmark (issue #15) — PROTOTYPE results

1707 candidate-box records across 10 samples (fields absent from ground truth excluded — see benchmark.py `ground_truth_marked`).

Threshold picked per method by sweeping all observed score values and maximizing overall F1 on the full pooled set (no held-out split — 10-sample prototype, not a claim of generalization).

## ink_density

Single global threshold=0.2304 (tuned on the full pooled set):

| group | precision | recall | F1 |
|---|---|---|---|
| **overall** | 0.9414 | 0.7828 | 0.8548 |
| ranged-radio-grid | 0.9429 | 1.0 | 0.9706 |
| circle-scale | 0.9375 | 0.2143 | 0.3488 |
| checkbox | 0.971 | 0.9853 | 0.9781 |
| radio | 0.875 | 0.9333 | 0.9032 |

Same detector, threshold tuned separately per field-type class:

| group | threshold | precision | recall | F1 |
|---|---|---|---|---|
| ranged-radio-grid | 0.2682 | 0.99 | 1.0 | 0.995 |
| circle-scale | 0.1095 | 0.9571 | 0.9571 | 0.9571 |
| checkbox | 0.2790 | 0.9853 | 0.9853 | 0.9853 |
| radio | 0.2794 | 0.9032 | 0.9333 | 0.918 |

## contour_morphology

Single global threshold=0.1998 (tuned on the full pooled set):

| group | precision | recall | F1 |
|---|---|---|---|
| **overall** | 0.6062 | 0.7266 | 0.661 |
| ranged-radio-grid | 0.5169 | 0.9293 | 0.6643 |
| circle-scale | 0.9333 | 0.2 | 0.3294 |
| checkbox | 0.7407 | 0.8824 | 0.8054 |
| radio | 0.6087 | 0.9333 | 0.7368 |

Same detector, threshold tuned separately per field-type class:

| group | threshold | precision | recall | F1 |
|---|---|---|---|---|
| ranged-radio-grid | 0.2003 | 0.5169 | 0.9293 | 0.6643 |
| circle-scale | 0.0638 | 0.9516 | 0.8429 | 0.8939 |
| checkbox | 0.2092 | 0.7407 | 0.8824 | 0.8054 |
| radio | 0.1998 | 0.6087 | 0.9333 | 0.7368 |

## tesseract_ink

Single global threshold=0.8750 (tuned on the full pooled set):

| group | precision | recall | F1 |
|---|---|---|---|
| **overall** | 0.208 | 0.7041 | 0.3211 |
| ranged-radio-grid | 0.1104 | 0.7475 | 0.1925 |
| circle-scale | 0.9565 | 0.6286 | 0.7586 |
| checkbox | 0.4902 | 0.7353 | 0.5882 |
| radio | 0.2326 | 0.6667 | 0.3448 |

Same detector, threshold tuned separately per field-type class:

| group | threshold | precision | recall | F1 |
|---|---|---|---|---|
| ranged-radio-grid | 0.8934 | 0.1113 | 0.7475 | 0.1937 |
| circle-scale | 0.1518 | 0.9706 | 0.9429 | 0.9565 |
| checkbox | 0.9204 | 0.5269 | 0.7206 | 0.6087 |
| radio | 0.9697 | 0.2714 | 0.6333 | 0.38 |

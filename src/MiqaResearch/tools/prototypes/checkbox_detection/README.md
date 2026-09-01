# PROTOTYPE — checkbox/radio detection on CPU (issue #15)

**Throwaway.** Answers the question in [#15](../../../.github) — not meant to ship as-is.
Candidate box coordinates in `boxes.py` are hand-derived from one sample's rendered
pages; real box provenance is issue #16's job.

## Run it

```
python tools/prototypes/checkbox_detection/benchmark.py
```

No Django needed — deliberately kept out of `MiqaResearch/tasks/` because that
package's `__init__.py` eagerly imports Django models. Needs `opencv-python-headless`,
`pytesseract` (both added to the project via `uv add`), and the `tesseract` CLI on
PATH (already installed on this machine at `/opt/homebrew/bin/tesseract`).

Renders all 10 real fixture scans at 200dpi, crops every in-scope candidate box,
scores each with 3 detectors, compares to `ground_truth.json`, writes
`raw_scores.json` (every score), `results.json`, and `results.md` (the
precision/recall/F1 tables) into this directory.

## What was tried

1. **`ink_density`** — Otsu-binarize the crop, trim a 6px border (drops the printed
   box outline itself), score = fraction of dark pixels in the interior.
2. **`contour_morphology`** — same binarize+trim, morphological close, score = area
   of the largest interior contour / interior area.
3. **`tesseract_ink`** — same binarize+trim, invert, `pytesseract.image_to_boxes`
   (glyph-shape boxes, not text recognition), score = boxed-glyph area / interior
   area.

Evaluated as binary "is this candidate box marked" classification across 1707
candidate boxes (10 samples × every ranged-radio/checkbox/radio option; fields the
respondent left entirely blank are excluded — see `ground_truth_marked` in
`benchmark.py`). Two mark styles are covered: X/tick/fill inside a printed square
(Q1–16, Q24) and a hand-drawn circle around a printed digit (Q17–23) — visually a
very different mark, kept in the eval because it's real in this form.

## Result: `ink_density` wins, and per-field-type thresholds matter a lot

With **one global threshold** (0.2304) tuned across all 1707 boxes, `ink_density`
gets overall F1 0.855, but circle-scale recall craters to 0.21 — the global
threshold sits right in the middle of the circle-scale marked-score cluster
(≈0.22–0.25), which is a smaller distribution offset than the box-mark clusters
because a hand-drawn circle covers less of its (deliberately generous, 56×56)
crop than an X fills a 38×38 box.

Tuning the threshold **separately per field-type class** instead of globally fixes
this — same detector, same code, just four thresholds instead of one:

| field-type class | threshold | precision | recall | F1 |
|---|---|---|---|---|
| ranged-radio grid (Q1–10, 0–10 boxes) | 0.2682 | 0.99 | 1.0 | 0.995 |
| circled-digit scale (Q17–23, 1–4) | 0.1095 | 0.957 | 0.957 | 0.957 |
| checkbox (multi-select) | 0.2790 | 0.985 | 0.985 | 0.985 |
| radio (single-select) | 0.2794 | 0.903 | 0.933 | 0.918 |

`contour_morphology` and `tesseract_ink` were both clearly worse across every
group at both global and per-group thresholds (see `results.md` for full tables) —
`contour_morphology`'s interior-contour-area signal is noisier than plain ink
density (a lot of false positives from stray pen pressure/paper texture), and
`tesseract_ink`'s glyph-box area is tuned for recognizable text, not X-marks/circles,
so it's unreliable except (interestingly) on the circle-scale group, where a
circled digit looks more like a real glyph to Tesseract.

## Error analysis: most residual errors aren't detector bugs

With per-field-type thresholds, `ink_density` misses 18/1707 (≈99% accuracy). Cross-
checking those 18 against each sample's `manifest.json` `ambiguous_marks`/
`half_checks_or_ambiguous_marks` notes: at least 9 of the 18 are cases the fixture
authors already flagged as **two physically-marked boxes in one field**, where
ground truth records only the one judged "authoritative" (e.g. sample_04 Q15/Q24:
both an X and a diagonal-hatch mark are present; sample_09 Q8: both '2' and '8' are
marked, '2' kept as primary). A pure ink-presence detector correctly reports both
boxes as marked — it has no way to know which one the annotator decided was
"the real answer", and shouldn't be expected to; that's a semantic/field-matching
concern, not a checkbox-detection one. The remaining handful look like genuine
registration drift on the few samples with heavier pen pressure (e.g. sample_04's
described "crosshatching, filled boxes" stress-test).

## Recommendation for the handoff spec (#19)

- Detector: **ink density inside a candidate box**, Otsu threshold, invert (ink =
  foreground), trim a 6px interior border to exclude the printed box outline before
  computing the dark-pixel fraction.
- **Threshold per field-type class, not one global threshold**: ~0.27 for
  ranged-radio-grid / checkbox / radio (boxes with a printed square outline),
  ~0.11 for circled-digit scales. In practice this just needs "is the candidate box
  a printed-square mark or a circled-digit mark", which field-matching (#16) already
  knows from the template's field type.
- Registration: candidate box pixel coordinates only transfer across samples after
  normalizing each rendered page to a common size per page index (phone-scan crop
  margins vary sample-to-sample even though rotational skew is minimal — see
  `benchmark.py: normalize_page_size`). The real pipeline will get box geometry from
  #16 rather than hardcoded coordinates, but #16 will likely need the same kind of
  per-page size/registration normalization this prototype needed.
- `contour_morphology` and `tesseract_ink` are not recommended as the primary
  signal; `tesseract_ink` alone is notably good specifically on circled-digit marks
  (F1 0.957) if a second opinion / fallback signal is ever wanted there.

# PROTOTYPE -- field matching without template geometry (issue #16)

**Throwaway.** Answers the question in #16 -- not meant to ship as-is. Builds on
issue #15's checkbox/radio detector (`prototype/issue-15-checkbox-detection`,
`tools/prototypes/checkbox_detection/detectors.py`), reimplemented here in
`detector.py` since that branch was never merged to `main`.

## Run it

```
python tools/prototypes/field_matching/benchmark.py
```

No Django needed (same reason as #15: `MiqaResearch/tasks/__init__.py` eagerly
imports Django models). Needs `opencv-python-headless`, `pytesseract` (added via
`uv add`) and the `tesseract` CLI with the `swe` language pack (already present
on this machine).

Renders all 10 real fixture scans at 200dpi, OCRs every page with Tesseract, runs
the field-matching pipeline described below, compares assigned values against
each sample's `ground_truth.json`, and writes `results.json` / `results.md` /
`raw_records.json` into this directory.

## The algorithm

1. **OCR** every page (`ocr_engine.py`): Tesseract word-level `image_to_data`,
   grouped into reading order by (block, par, line). Punctuation-only tokens
   (Tesseract routinely misreads empty printed checkbox squares as `"[]"`,
   `"--"`, `"|"`) are dropped at this stage -- see "Known failure modes" below
   for why that matters more than it sounds.
2. **Field-label localization** (`pipeline.py: localize_field_anchors`): for
   every field in the template, in document order, slide fixed-word-count
   windows over each page's OCR words and score each against the field's label
   with `difflib.SequenceMatcher` (best of a diacritics-preserved and a
   diacritics-stripped comparison -- Swedish å/ä/ö are meaningful letters, not
   accents to always strip, but Tesseract does sometimes mangle them).
   Independently searching **all 4 pages** per field, rather than assuming a
   fixed page index, is what makes this survive sample_09's swapped pages (see
   below) -- and it doubles as "section/group ordering as a prior" once combined
   with the next step.
3. **Document-order tie-break**: some fields have near-duplicate label text
   across sections (Q15 and Q24 differ in exactly one word of a ~130-character
   sentence). On noisy OCR the *wrong* page's clean real text can outscore the
   *right* page's OCR-mangled real text. Fields with a clear top-page winner
   (margin >= 0.08 over the runner-up) are "confident" and vote; an ambiguous
   field defers to the majority page among nearby confident fields (+/-4 in
   template order) when one of its own candidate pages agrees closely enough.
   This is a direct, load-bearing use of the issue's "section/group ordering as
   a prior" -- without it, Q15/Q24 (and Q25's free-text label) land on the wrong
   page outright.
4. **Region carving** (`compute_field_regions`): once every field has a page +
   anchor bbox, fields on the same page are ordered by vertical position; each
   field's search region runs from its own anchor's bottom edge to the next
   field's anchor's top edge (full page width). A field whose neighbor
   computation produces an inverted range (a multi-line-wrapped label's own
   bbox extending past where the next field's anchor starts -- two genuine spans
   crossing, not a bug in either one) falls back to a minimum-height region
   rather than silently losing all its options.
5. **Option/digit sub-anchor localization**: within a field's region,
   checkbox/radio option labels are located the same way as field labels
   (windowed fuzzy match); ranged-radio digits (0-10 grid, or 1-4 circled scale)
   are located by regex-matching bare digit tokens and sorting by x-position,
   zipped positionally against the template's option order.
6. **Box discovery** (`geometry.py`): printed box outlines are found globally
   per page via OpenCV contour detection (`RETR_EXTERNAL`, size/aspect filter,
   calibrated to ~24-48px squares at 200dpi -- no "hollow vs filled" shape test,
   since a thin outline and an X-marked box have near-identical outer-contour
   fill fraction; that distinction is issue #15's detector's job, not this
   step's). Each option/digit anchor searches for its box "directly above" first
   (ranged-radio grid layout: box sits above its digit), then "directly left"
   (checkbox/radio layout: box sits left of its label), then a small-radius
   fallback. Circled-digit fields (Q17-23) have no separate box glyph -- the
   digit's own OCR bbox, dilated, is the candidate.
7. **Mark detection**: issue #15's ink-density detector, but crops a *fixed*
   canonical size (38px, matching #15's hand-measured box size) centered on the
   discovered box rather than the box's own (variable) contour bounding rect --
   a heavy X mark's ink bleeding past the printed outline inflates the raw
   contour size and dilutes density scoring otherwise (found while debugging a
   near-miss: a genuine mark scored 0.2649 against a 0.2682 threshold).
8. **Threshold recalibration**: #15's thresholds were tuned on hand-labelled
   fixed-size crops; this pipeline's boxes come from a different path (contour
   discovery + re-centering), so scores don't transfer 1:1. Same sweep-for-best-
   F1 methodology as #15, applied to *this* pipeline's own scores (pooled across
   all 10 samples, no held-out split -- a prototype calibration, not a
   generalization claim). See results.md for both #15's-thresholds-verbatim and
   recalibrated numbers.

## Results

Full tables in `results.md` / `results.json`. Headlines:

- **Label localization hit rate: 96.2%** (356/370 field-anchors, all field
  types, all 10 samples) -- the core semantic-matching + page-search + document-
  order-prior approach works well.
- **sample_09's swapped pages are handled correctly with zero special-casing.**
  Spot check: `prom101_q12_anvander_bloja` lands on page 3 in sample_09 vs page 2
  in every other sample; `prom101_q17_urinera_ofta_dagen` lands on page 2 in
  sample_09 vs page 3 elsewhere -- exactly matching the manifest's documented
  swap, recovered purely by searching all pages per field rather than trusting a
  fixed index.
- **Value assignment (recalibrated thresholds) is weak: checkbox 13.5%, radio
  10%, ranged-radio-grid 24.2%, circle-scale 1.4%.** This is the honest,
  disappointing half of the result -- label/section matching (the question #16
  actually asks) works; layering box discovery + mark detection on top of
  auto-found boxes (rather than #15's hand-given ones) does not yet reach usable
  accuracy. See "Known failure modes" for why, and "Recommendation" for what
  would fix it.

## Known failure modes

- **Radio fields with short or highly similar option labels localize their
  options poorly.** `prom101_q12_anvander_bloja` ("Nej"/"Ja") and the two
  7-point `..._livskvalitet` scales ("Mycket nöjd"/"Nöjd"/"Ganska nöjd"/...) are
  the weakest group (10% accuracy even recalibrated) -- short option text is
  easy to miss entirely, and near-duplicate option text across a 7-way choice is
  easy to assign to the wrong option even when *an* anchor is found.
- **A multi-line-wrapped label's anchor can legitimately overlap the next
  field's anchor**, since both are real spans on the page that happen to cross
  (region-carving falls back to a minimum-height window in that case -- see step
  4 above -- but this is a coarser signal than a clean non-overlapping split
  would give).
- **This form's checkbox/radio grids OCR as garbage text on the same Tesseract
  line as adjacent question text** (Tesseract's PSM 6 misreads empty printed
  squares as things like "Od"/"MH"/"DO" and folds them into the surrounding
  line). Two targeted fixes were needed for this: dropping punctuation-only OCR
  tokens (they normalize away to nothing during *scoring* but were still
  corrupting anchor *bounding boxes*), and recentering box crops on a canonical
  size rather than the raw discovered contour. Two *rejected* fixes are also
  worth recording so they aren't retried: restricting label-match windows to a
  single OCR line (made things worse -- Tesseract's own line assignment is
  already unreliable here, so this just added a second, differently-wrong
  boundary), and a hard cap on a candidate window's bounding-box height
  (rejected too many legitimate matches to word-position jitter, e.g. from
  diacritics).

## Escalation contract

The code implements a first-pass contract (`pipeline.py: escalate`): escalate a
field if its anchor wasn't found (score < 0.55), or -- for checkbox/radio/
ranged-radio fields -- if option-localization rate < 0.7, or multiple marks are
ambiguous on a single-select field, or the discovered option count deviates from
the template's expected count by more than ~20%.

**Measured against ground truth, that contract is not conservative enough**: of
the 236 in-scope box-mark fields across all 10 samples, 85 were accepted as
"classic path succeeded" (not escalated) -- but 67 of those 85 (79%) were
actually wrong. The contract as coded catches missing/weak *localization*
reliably; it does not catch *wrong mark detection on a field that localized
fine*, which turns out to be the dominant failure mode here.

**Revised recommendation for the #19 handoff spec**, informed by this
prototype's measured per-group accuracy:

- Always escalate `circle-scale` (Q17-23) and `radio` value assignment --
  measured accuracy (1.4% and 10%) is far below any threshold worth trusting
  automatically.
- Escalate `ranged-radio-grid` and `checkbox` value assignment unless *all* of:
  option-localization rate == 1.0 (not merely >= 0.7), label-match score >=
  0.85, and exactly one mark cleared the group's recalibrated threshold with a
  clear margin (e.g. >= 1.5x the runner-up score) -- these two groups reach
  higher recalibrated F1 (0.72 and 0.42) but still need a much stricter bar than
  originally coded before they're trustworthy unescalated.
- Field/section/page localization (this prototype's actual strength) does not
  need an escalation path of its own at 96% -- but a field whose anchor wasn't
  found at all (currently already covered) should always escalate, since
  everything downstream depends on it.
- In short: **this classic path is currently good for telling the VLM fallback
  *where* to look (which page, which region), not yet reliable for deciding *what
  was marked there*.** That's a materially different (and more modest) role than
  "classic-path-primary, VLM-fallback-for-edge-cases" -- worth flagging
  explicitly for #18/#19 rather than assuming the original charting-stage
  split holds as measured.

## Backup path: label-text registration against a blank-form PDF

Not implemented in this prototype -- there is no blank-form PDF file anywhere in
this repo to exercise it against (the filled PDF used to author the template in
#12 was removed once the template JSON existed; it's the same content as
sample_01, not blank). Per the issue, this path is conditional on the user
supplying one.

**Trigger condition** (for the #19 handoff spec): use blank-PDF label-text
registration instead of plain semantic matching only when a sample's label-
localization hit rate falls below a firm floor (e.g. < 80%, well below this
prototype's measured 96.2% median case) *and* a blank template PDF has been
supplied for that form. Do not attempt registration without a supplied blank
PDF -- kpforms cannot render the template server-side (browser-side only, per
#11), so there is no fallback source of page geometry to register against.

## Recommendation for #19

1. Ship label/section/page localization as designed here -- it measurably works
   (96.2% hit rate, correct under a real page-swap).
2. Do **not** ship this prototype's box-discovery + mark-detection value
   assignment as the classic path's final answer; per the escalation contract
   above, route nearly all value assignment to the VLM fallback until a better
   box-localization method is built. Likely next step: rather than discovering
   boxes generically per-page, calibrate box positions once per *field type*
   against the template's own printed layout conventions (this form is
   internally consistent: grid rows always put the box above the digit, options
   always put the box left of the label) combined with tighter per-option
   anchor-to-box distance rules than this prototype's generic radius search.
3. Radio fields with many similar-looking options (the two 7-point
   `..._livskvalitet` scales) are the single weakest spot end-to-end and deserve
   dedicated attention regardless of the box-localization fix above.

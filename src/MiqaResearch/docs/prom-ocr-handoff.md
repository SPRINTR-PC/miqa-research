# PROM OCR pipeline — handoff spec

Destination artifact for #19. Consolidates every decision made across #10–#18 into one buildable spec for `run_ocr_on_prom_data`. This whole epic is plan-don't-do (#10): nothing in this doc is implemented yet except where explicitly noted as "already shipped." The implementing session should not need to re-open any of #11–#18 — open questions that remain are called out at the end.

Scope reminder from #10: one PROM form template in scope (`PROM_1_PRO_GI_GU_SWE`), CPU-only, acceptance = ≥95% field-level accuracy and ≤2 min/page for the **classic path** on modest CPU (4 cores). The VLM fallback is exempt from the 2 min/page bar (#18) but must never hang the task.

## 1. Pipeline overview

```
PromData.prom_form_file
  │
  ▼
[1] Input normalization  — PDF → per-page raster (existing convert_pdf_to_image), image passthrough
  │
  ▼  (per page, independently — one page's failure must not abort the others)
[2] Classic OCR           — Tesseract (swe+eng), preprocessing per #15/#16
  │
  ▼
[3] Field matching         — #16: fuzzy label-anchor search across ALL pages, per-field
  │
  ▼
[4] Mark detection          — #15: ink-density threshold on matched boxes (checkbox/radio/ranged-radio/circle-scale)
  │
  ▼
[5] Escalation decision      — #18: per-field trigger → batched per-page VLM call
  │        │
  │        ▼ (only if ≥1 field on the page escalated)
  │    VLM fallback call (qwen3-vl:8b-instruct-q8_0, one call per escalated page)
  │        │
  ▼        ▼
[6] Merge                     — #18: VLM fills only escalated fields; post-processing guards; extraction_flags
  │
  ▼
[7] kpforms validation          — _validate_form_submission_against_template (#11/#13, NOT submit_form_data)
  │
  ▼
[8] Store                        — new ParsedPromForm row (append-only, #13)
```

Stage [1] happens once for the whole form. Stages [2]–[5] run per page but all pages' field-matching results are needed before merge, since #16's anchor search spans all pages regardless of which page a field is nominally on (this is precisely what recovers sample_09's swapped-page case with zero special-casing — do not reintroduce a fixed page→section assumption anywhere in this pipeline).

## 2. Dependencies & settings

### New dependencies (add to `pyproject.toml`)

- `pytesseract` — Tesseract Python wrapper.
- `opencv-python-headless` — headless build; the server has no display, and the GUI build pulls unneeded system libs.
- `pillow` — explicit dependency; `pytesseract` needs `PIL.Image` objects and nothing currently in the project pulls it in.

### New system package (Dockerfile, final stage, before `COPY . .`)

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-swe \
    && rm -rf /var/lib/apt/lists/*
```

**Naming gotcha, verify before installing anything**: #10's epic notes say "swa+eng langdata." **`swa` is Swahili's ISO 639-2 code, not Swedish's — Swedish is `swe`.** The Debian/Ubuntu package and Tesseract traineddata file are `tesseract-ocr-swe` / `swe.traineddata`. Installing `tesseract-ocr-swa` would silently give the pipeline Swahili language data on a Swedish form. Use `swe` everywhere (`pytesseract.image_to_string(img, lang="swe+eng")`).

### Settings (`MiqaResearch/settings.py`)

- **Fix the broken default**: `MIRES_OLLAMA_MODEL` default changes from `"gemma4"` (line 77 — does not exist on the Ollama registry, confirmed in #17) to `"qwen3-vl:8b-instruct-q8_0"` (#18 §3).
- **New env vars**, same `django-environ` pattern as the existing `MIRES_OLLAMA_*` block:
  - `MIRES_OCR_VLM_PAGE_TIMEOUT_SECONDS` (int, default `900`) — per-VLM-call timeout (#18 §4).
  - `MIRES_OCR_VLM_FORM_TIMEOUT_SECONDS` (int, default `2700`) — total fallback budget per form (#18 §4).

### Celery task time limit — a real conflict, not yet addressed anywhere in #10–#18

`MIRES_CELERY_TASK_TIME_LIMIT` defaults to **30 minutes** (`MiqaResearch/settings.py:49`) and applies globally to every task, including `QUEUE_OCR`. Worst case for one form under this spec is classic path (≤2 min/page × up to 10 pages = 20 min) **plus** the VLM fallback ceiling (45 min) ≈ **65 minutes** — Celery would hard-kill (`SIGKILL`, no exception handling possible) the task well before that, which is exactly the silent-hang failure mode #10 says must not happen, just arriving from the opposite direction (killed too early instead of running forever).

Fix: override the limit on this specific task rather than raising the global default (other tasks on other queues shouldn't need 65+ minutes):

```python
@app.task(queue=QUEUE_OCR, time_limit=4500, soft_time_limit=4200)  # 75min hard / 70min soft
def run_ocr_on_prom_data(prom_data_id): ...
```

Catch `celery.exceptions.SoftTimeLimitExceeded` around the per-page loop so a form that's about to be hard-killed still gets a chance to persist whatever pages completed (with remaining fields flagged `failed` per #18 §5) instead of losing the whole run.

## 3. Module layout

`MiqaResearch/tasks/ocr.py` currently contains everything inline (input handling, prompt building, Ollama call, save) using the wrong settings names (`settings.OLLAMA_URL`/`OLLAMA_MODEL` — those happen to be correct, but the prompt/merge logic is the pre-#16/#17/#18 placeholder and needs a full rewrite, not a patch). Recommended split — the Celery task becomes a thin entrypoint, the pipeline logic is plain, independently-testable Python:

```
MiqaResearch/ocr/
    __init__.py
    preprocessing.py    # PDF/image → per-page raster; convert_pdf_to_image moves here unchanged
    field_matching.py   # #16: label-anchor search, region carving, box discovery
    mark_detection.py    # #15: ink-density detector, per-field-type-class thresholds
    vlm_fallback.py      # #18: escalation predicate, batched per-page prompt, post-processing guards
    merge.py             # #18 §5: combine classic + VLM, extraction_flags
    validation.py        # thin wrapper around kpforms' _validate_form_submission_against_template
    pipeline.py          # orchestrates the above; run_pipeline(prom_data) -> (data, fieldsOutOfTolerance, extraction_flags)

MiqaResearch/tasks/ocr.py   # @app.task run_ocr_on_prom_data — loads PromData, calls ocr.pipeline.run_pipeline, saves ParsedPromForm
```

Throwaway prototype branches exist for two of these — mine the algorithms, don't merge the branches as-is:
- `prototype/issue-15-checkbox-detection` → `mark_detection.py` (ink-density detector + thresholds are the shipped recommendation).
- `prototype/issue-16-field-matching` → `field_matching.py` for the **label/anchor/page-search algorithm only** (96.2% measured hit rate — reuse this part). Its box-discovery + mark-assignment code is the explicitly-rejected part (13.5–24.2% accuracy) — do not port that half; per §5 below almost all value assignment goes through VLM fallback until a better box-localization method exists.

## 4. Stage detail

### [1] Input normalization

Reuse `convert_pdf_to_image` (pymupdf) unchanged for PDFs; pass image files straight through as a single-page list. Render at **300 DPI** — this is what the existing helper already does and what #15/#16's prototypes were tuned against. Keep the rendered `pixmap` per page in memory for reuse across stages [2]–[5]; don't re-render per stage.

For VLM calls specifically (stage [5]), **downsample the 300 DPI pixmap to ~200 DPI equivalent before base64-encoding.** #17's benchmark (accuracy numbers and the latency table this spec's budgets are built on) used 200 DPI page renders — sending full 300 DPI images would increase image-token count and latency beyond what was actually measured, without a corresponding accuracy validation.

### [2] Classic OCR (Tesseract)

`pytesseract.image_to_data(img, lang="swe+eng", output_type=Output.DICT)` (word-level, with confidences — needed for the non-mark-type escalation trigger in §5) per page. Preprocessing before OCR, per #15/#16's prototypes: deskew (minimal skew across all 10 samples, so a light affine correction, not a heavy pipeline), Otsu binarization.

### [3] Field matching (#16)

Port the anchor-search algorithm only (see §3). For each template field, fuzzy-match its label against OCR words **across all pages of the form**, not a fixed page index — document-order tiebreak for near-duplicate labels. Emit, per field: matched page index, region bounding box, `label_match_score`. This is the part that measured 96.2% (356/370) — ship as designed, no further validation needed before use.

### [4] Mark detection (#15)

Given a field's region (from §[3]) and its type, locate candidate box/digit outlines (OpenCV contour detection) and score with ink-density thresholding — Otsu-binarize the crop, invert, trim a 6px interior border, dark-pixel fraction. **Field-type-specific thresholds, not one global value** (measured, do not re-tune without new data):

| field-type class | threshold |
|---|---|
| ranged-radio grid | 0.2682 |
| circled-digit scale | 0.1095 |
| checkbox (multi-select) | 0.2790 |
| radio (single-select) | 0.2794 |

Normalize each rendered page to a common size per page index before applying any hand-derived-style coordinate logic — #15 found phone-scan crop margins vary sample-to-sample even with minimal skew, and #16 needs the same normalization for its own box discovery. Emit per field: `option_localization` (fraction of expected option boxes actually found), `mark_margin_ratio` (winning candidate's ink-density score ÷ runner-up's).

Note the split responsibility this measured: mark detection *given a correctly-located box* is ~99% accurate (#15, hand-derived boxes); the weak link measured in #16 was auto box-discovery from the anchor region, not this detector. Don't let a low end-to-end number here read as "the detector is bad" — it's the localization feeding it.

### [5] Escalation decision + VLM fallback (#18)

**Per-field trigger** (evaluated using the signals from stages [3]/[4]):

```python
def should_escalate(field) -> bool:
    if field.label_match_score < 0.55:
        return True  # anchor not found — nothing downstream is usable
    if field.field_type in ("radio", "circle-scale"):
        return True  # measured classic accuracy 10% / 1.4% — not a threshold case
    if field.field_type in ("checkbox", "ranged-radio-grid"):
        return not (
            field.option_localization == 1.0
            and field.label_match_score >= 0.85
            and field.mark_margin_ratio >= 1.5
        )
    if field.field_type in ("text", "numeric", "string", "datetime"):
        # not covered by #16's measured contract (few such fields in this form) —
        # same fail-open principle, applied by analogy. Revisit once measured.
        return field.tesseract_word_confidence < 60 or not field.parses_as_expected_format
    return False
```

Expect this to escalate the large majority of value-assignment fields in practice — per #16's own conclusion, the classic path's current, honest role is field *localization*, not value *extraction*.

**Batching**: group escalated fields by page. For each page with ≥1 escalated field, issue **one** VLM call for that whole page (not one call per field) — asking about the full field-set anchored to that page (matches #17's exact benchmarked prompt/accuracy numbers, and lets the checkbox-consistency guard below see paired fields in the same response). Only the flagged fields' answers are taken from the response; non-escalated fields on the same page keep their classic-path value untouched.

**Prompt**, reusing #17's design: `model="qwen3-vl:8b-instruct-q8_0"`, `format="json"`, `num_ctx=16384` minimum, field subset = fields anchored to this page (id, label, type, option values/labels for choice fields), instruct the model to omit fields not visible on the page. `num_gpu: 0` (server is CPU-only — Ollama defaults to GPU offload if one is present, which this deployment never has, but pin it explicitly rather than relying on absence of hardware).

**Post-processing guards, apply to every VLM response before merge**:
1. Drop any returned `fieldId` not in the template's known id set (hallucination guard).
2. Diacritic-folded label→value lookup for choice fields (recovers display-label vs schema-value mismatches, ~1pp, cheap).
3. Flag/reject any value that exactly echoes a literal example string from that field's own `description` (placeholder-text hallucination — e.g. a blank staff-only date field getting filled with the `"t.ex. 20250515"` hint text verbatim).
4. Checkbox consistency: if a paired free-text sub-field (e.g. `..._annat_text`) has a non-null value in this response, ensure its parent checkbox option is included in the checkbox field's value set even if the model didn't select it.

**Timeouts** (see §2): per-call timeout `MIRES_OCR_VLM_PAGE_TIMEOUT_SECONDS`; running total against `MIRES_OCR_VLM_FORM_TIMEOUT_SECONDS` across the form. Once the form ceiling is hit, stop issuing further VLM calls — any field still pending escalation is recorded as `failed` (§[6]), not run.

### [6] Merge (#18 §5)

- VLM fills only the fields flagged for escalation on that page; never overwrites a non-escalated field's classic-path value.
- `ranged-radio` VLM answers are authoritative once they clear the guards above (not merely a hint) — `qwen3-vl:8b-instruct-q8_0` measured 100% on this type in #17's final benchmark, reversing the earlier `qwen2.5vl`-based caution. Classic mark-detection stays the first attempt purely to avoid model latency, not because the VLM is distrusted here.
- Free-text fields sourced from the VLM are always tagged low-confidence in `extraction_flags`, regardless of whether they passed the guards — 42% exact-match accuracy never clears an auto-accept bar on its own, even though many are near-miss-usable for a human reviewer.
- **Double failure** (classic didn't clear its bar **and** the VLM answer is missing or guard-rejected) → `value: null` in the kpforms `data` array, plus an entry in `extraction_flags` (new field, §5 of #10's data model — see below) so it reads as "extraction failed," not "field was blank on the paper form."

`extraction_flags` shape (JSON, keyed by `fieldId`):

```json
{
  "prom101_q15_livskvalitet": {"source": "classic", "confidence": "high"},
  "prom101_q17_urinera_ofta_dagen": {"source": "vlm", "confidence": "high"},
  "prom101_q16_storsta_problem": {"source": "vlm", "confidence": "low"},
  "prom101_studie_id": {"source": "failed", "attempted": ["classic", "vlm"]}
}
```

### [7] kpforms validation

Call `_validate_form_submission_against_template(form_data, template_schema)` directly (kpforms private function — #11's documented, accepted quirk-workaround). **Never** `submit_form_data` / create a `FormSubmission` — OCR output is a machine-drafted candidate reading, not a real submission, and the required-field rejection + int/UUID pk mismatch both rule it out (#11, #13). Store `validated_data.model_dump(mode="json")` (the `{data, fieldsOutOfTolerance}` shape) into `ParsedPromForm.data`.

### [8] Store

New `ParsedPromForm` row per OCR run — **append-only, never upsert** (#13): once a row is human-validated (`validated_by`/`validated_at` set), a re-run must not silently overwrite it. "Latest OCR reading for a `PromData`" = newest row for that `prom_file`.

## 5. Data model changes needed (handoff detail — not applied by this spec, for #19's implementing session)

Three additive migrations, all previously flagged and none yet implemented in the current codebase (verified — `PromData`/`ParsedPromForm` in `MiqaResearch/data/models/prom_data.py` don't have them today):

1. `PromData.template_version: IntegerField` (#13) — captured at upload time from `prom_data.prom_form_template.template.version`. Mirrors kpforms' own `FormSubmission.form_template_version` convention. Backfill existing dev rows via `RunPython` in the same migration, keep the column non-nullable.
2. `ParsedPromForm.created_at: DateTimeField(auto_now_add=True)` (#13) — needed because `Meta.ordering = ["-validated_at"]` sorts by *review* time (null until reviewed), not parse time, so "latest run for this file" isn't well-defined without it. Reorder `Meta.ordering` to `["prom_file", "-created_at"]` once added.
3. `ParsedPromForm.extraction_flags: JSONField` (#18, this spec §4[6]) — additive, never read by kpforms validation, purely a provenance/confidence signal for downstream review.

## 6. Template authoring + import — already shipped, reference only

`PROM_1_PRO_GI_GU_SWE` is authored and importable today (#12) — no work needed here:
- Template JSON: `tests/example_data/prom_data/templates/PROM_1_PRO_GI_GU_SWE.json`.
- Import command: `MiqaResearch/data/management/commands/import_prom_form_template.py` (`python manage.py import_prom_form_template`), idempotent by name, creates both the kpforms `FormTemplate` and the `PromFormTemplate` wrapper row.
- Covered by `tests/test_import_prom_form_template_command.py`.

## 7. Evaluation harness

Fixture set (#14, already collected): `tests/example_data/prom_data/prom_samples/sample_01`…`sample_10`, each with `scan.pdf`, `ground_truth.json` (kpforms-native `{data: [...]}`), `manifest.json` (quality notes).

**Known fixture bug (#17)**: the top-level `tests/example_data/prom_data/prom_samples/manifest.json`'s embedded `scan_path`/`ground_truth_path` fields point at a nonexistent `tests/fixtures/prom_samples/...`. **Don't fix those fields and don't trust them** — build the harness to derive paths directly from `sample_id` (`tests/example_data/prom_data/prom_samples/{sample_id}/scan.pdf` etc.), which sidesteps the bug entirely rather than requiring a 10-entry edit that could drift again.

New management command, `evaluate_prom_ocr` (same style as `import_prom_form_template`):
- Runs the full pipeline (§4) over all 10 samples.
- Scores field-level accuracy against `ground_truth.json` using #17's exact normalization (Unicode NFKC + casefold; checkbox/multi-select compared as sets) — reuse this so numbers stay comparable to the benchmark #18's design is built on.
- Times each page (classic path only, and separately, wall-clock including any VLM escalation) to check the ≤2 min/page classic-path bar.
- Prints a per-sample and overall report (accuracy, latency, escalation rate, `extraction_flags` breakdown by source) — same shape as #16/#17's `results.md`/`results.json`, so this doc's numbers and the harness's output stay directly comparable.
- Exits non-zero if overall accuracy < 95% or mean classic-path latency > 2 min/page, so it doubles as a CI-style gate once wired up.

**This harness has not been run against a real implementation yet — nothing in this repo currently meets the 95%/2-min bar**, because nothing implementing #16–#18's design exists yet. Running it is how the implementing session finds out where it actually lands, not a number this spec can predict. Do not treat any accuracy figure quoted elsewhere in #16/#17 as the pipeline's number — those were prototype-only or full-page-VLM-only measurements, not this merged pipeline's.

## 8. Failure & edge-case handling

- **Unreadable/low-confidence field**: escalates per §4[5]; if the VLM answer is also missing/rejected, `value: null` + `extraction_flags[...] = {"source": "failed", ...}` (§4[6]/§5). Never raise — a partially-unreadable form is the expected case, not an error.
- **Blank page** (no anchors found at all): contributes nothing to field matching from that page; fields normally anchored there fall through to the anchor-not-found escalation rule (§4[5]) like any other localization failure. No special-case handling needed — this is already the generic "label-match < 0.55" path.
- **Page order** (sample_09's swapped pages): handled entirely by #16's all-pages anchor search (§4[3]) — do not add page-order logic anywhere else in the pipeline; that would just reintroduce the fixed-index assumption #16 deliberately avoided.
- **Both paths failing on the same field**: `value: null` + `extraction_flags[fieldId] = {"source": "failed", "attempted": [...]}` — this is the double-failure representation #18 specifically asked for; downstream validation/human review keys off `extraction_flags`, not the bare `null`.
- **One page's classic-path stage throwing** (e.g. a corrupt render): catch per-page, log, treat that page as contributing zero fields (same effect as a blank page) rather than aborting the whole multi-page form.
- **Task-level timeout**: `SoftTimeLimitExceeded` (§2) → persist whatever's completed with remaining fields flagged `failed`, rather than losing the run to a hard kill.

## 9. Open items for the implementing session (not resolved by #10–#18, flagged not guessed)

- Non-mark field types' (`text`/`numeric`/`string`/`datetime`) escalation thresholds (§4[5]) are reasoned by analogy to #16's contract, not measured — this form has few such fields. Revisit once the harness (§7) has real numbers.
- All latency figures (#17) were measured on an Apple M5 Max pinned to 4 threads, `num_gpu: 0` — explicitly flagged there as optimistic vs. the actual target server CPU. The timeout budgets in §2 carry that same uncertainty forward; re-measure on real target hardware and adjust `MIRES_OCR_VLM_*_TIMEOUT_SECONDS` before relying on them in production.
- `MiqaResearch/interfaces/http/api/views/upload_data/upload_prom_data.py` is currently an empty stub (`from django.views import View`) — wiring the upload endpoint to actually enqueue `run_ocr_on_prom_data` is outside this epic's sub-issues and isn't specified here.

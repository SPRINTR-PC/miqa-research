"""VLM escalation stage.

Per-field escalation trigger (#18 §4[5]), batched into one VLM call per page
that has at least one escalated field (not one call per field), plus
post-processing guards on the response (#18 §4[2]). Resilient to Celery's
soft time limit firing mid-loop: stops immediately (rather than retrying a
doomed call) and returns whatever pages already completed, so run_pipeline
still has time to reach merge/validation/save before the hard kill (#51).
"""

import base64
import io
import json
import re
import time
import unicodedata
from dataclasses import dataclass

import httpx
import pymupdf
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from kpforms.form_schema import FormTemplateSchema
from PIL import Image

from . import mark_detection
from .field_matching import MARK_FIELD_TYPES, MIN_ANCHOR_SCORE, FieldMatch
from .mark_detection import MarkResult

# #16's escalation contract (#18 §4[5]) -- do not re-tune without new data.
LABEL_MATCH_CONFIDENT = 0.85
MARK_MARGIN_CONFIDENT = 1.5
OPTION_LOCALIZATION_CONFIDENT = 1.0

# Not covered by #16's measured contract (this form has few non-mark fields) --
# same fail-open principle, applied by analogy. Revisit once measured
# (docs/prom-ocr-handoff.md §9).
TEXT_CONFIDENCE_THRESHOLD = 60.0

_DATE_RE = re.compile(r"\d{8}")
_NUMERIC_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_EXAMPLE_HINT_RE = re.compile(r"t\.ex\.?\s*([^\s.,;]+)", re.IGNORECASE)
_QUESTION_PREFIX_RE = re.compile(r"^(.*?_q\d+)")

RENDER_DPI = 300  # pages arrive already rendered at this DPI (#44)
VLM_DPI = 200  # matches #17's benchmarked conditions -- downsample before sending


@dataclass
class VlmResult:
    field_id: str
    value: str | list[str] | None = None
    confidence: str = "low"


# ---------------------------------------------------------------------------
# Escalation trigger (#18 §4[5])
# ---------------------------------------------------------------------------


def _parses_as_expected_format(match: FieldMatch) -> bool:
    if not match.text_value:
        return False
    if match.field_type == "datetime":
        return bool(_DATE_RE.search(match.text_value))
    if match.field_type == "numeric":
        return bool(_NUMERIC_RE.search(match.text_value))
    return True  # string/text: no strict format, confidence is the only signal


def should_escalate(match: FieldMatch, mark_result: MarkResult | None) -> bool:
    if match.label_match_score < MIN_ANCHOR_SCORE:
        return True  # anchor not found -- nothing downstream is usable

    if match.field_type not in MARK_FIELD_TYPES:
        return match.tesseract_word_confidence < TEXT_CONFIDENCE_THRESHOLD or not _parses_as_expected_format(match)

    group = mark_detection._group_for(match.field_type, len(match.options))
    if group in ("radio", "circle-scale"):
        return True  # measured classic accuracy 10% / 1.4% -- not a threshold case

    if mark_result is None:
        return True
    return not (
        mark_result.option_localization >= OPTION_LOCALIZATION_CONFIDENT
        and match.label_match_score >= LABEL_MATCH_CONFIDENT
        and mark_result.mark_margin_ratio >= MARK_MARGIN_CONFIDENT
    )


def _escalated_fields_by_page(
    field_matches: list[FieldMatch], mark_results: dict[str, MarkResult]
) -> dict[int, list[FieldMatch]]:
    by_page: dict[int, list[FieldMatch]] = {}
    for match in field_matches:
        if match.page_index is None:
            continue
        if should_escalate(match, mark_results.get(match.field_id)):
            by_page.setdefault(match.page_index, []).append(match)
    return by_page


# ---------------------------------------------------------------------------
# Prompt (#17's design, narrowed to #16's per-page field subset per
# docs/prom-ocr-handoff.md §4[5])
# ---------------------------------------------------------------------------


def _flatten_template_fields(template_schema: FormTemplateSchema) -> dict[str, object]:
    return {
        input_field.id: input_field
        for section in template_schema.sections
        for group in section.inputGroups
        for input_field in group.fields
    }


def _field_options(input_field) -> list[tuple[str, str]]:
    if input_field.type in ("checkbox", "radio"):
        return [(o.value, o.label) for o in input_field.options]
    if input_field.type == "ranged-radio":
        return [(o.value, o.label) for o in input_field.optionLabelsAndIndices]
    return []


def _field_prompt_entry(input_field) -> dict:
    entry = {"id": input_field.id, "label": input_field.label, "type": input_field.type}
    options = _field_options(input_field)
    if options:
        entry["options"] = [{"value": value, "label": label} for value, label in options]
    return entry


def _build_prompt(page_template_fields: list) -> str:
    fields_json = json.dumps([_field_prompt_entry(f) for f in page_template_fields], ensure_ascii=False)
    return (
        "You are extracting handwritten and marked answers from one page of a scanned "
        "Swedish patient questionnaire. For each field below, read the page image and "
        "report the value actually visible on it. Omit a field entirely if it is not "
        "visible on this page. Never guess or fill in a value from memory, or from a "
        "field's own example/hint text -- only report what is actually marked or "
        "written on the page.\n\n"
        f"Fields:\n{fields_json}\n\n"
        'Return strict JSON in exactly this shape: {"data": [{"fieldId": "...", "value": "..."}]}'
    )


def _encode_page_for_vlm(pixmap: pymupdf.Pixmap) -> str:
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    scale = VLM_DPI / RENDER_DPI
    resized = image.resize((round(image.width * scale), round(image.height * scale)))
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _call_ollama(prompt: str, image_b64: str, timeout: float) -> dict:
    response = httpx.post(
        f"{settings.OLLAMA_URL}/api/generate",
        json={
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "format": "json",
            "options": {"num_ctx": 16384, "num_gpu": settings.OCR_VLM_NUM_GPU},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return json.loads(response.json().get("response", "{}"))


# ---------------------------------------------------------------------------
# Post-processing guards (#18 §4[2])
# ---------------------------------------------------------------------------


def _diacritic_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def remap_choice_value(value, options: list[tuple[str, str]]):
    """Guard: diacritic-folded label -> value lookup for choice fields (the
    model sometimes returns a display label instead of the schema value)."""
    known_values = {option_value for option_value, _label in options}
    label_to_value = {_diacritic_fold(label): option_value for option_value, label in options}

    def remap_one(candidate):
        if candidate in known_values:
            return candidate
        return label_to_value.get(_diacritic_fold(str(candidate)), candidate)

    if isinstance(value, list):
        return [remap_one(v) for v in value]
    return remap_one(value)


def _example_hint(description: str | None) -> str | None:
    if not description:
        return None
    match = _EXAMPLE_HINT_RE.search(description)
    return match.group(1).rstrip(".") if match else None


def echoes_placeholder_example(value, description: str | None) -> bool:
    """Guard: reject a value that exactly echoes the field's own example/hint
    text (e.g. a blank staff-only date field filled with "t.ex. 20250515")."""
    hint = _example_hint(description)
    return hint is not None and value is not None and str(value).strip().rstrip(".") == hint


def _question_prefix(field_id: str) -> str | None:
    match = _QUESTION_PREFIX_RE.match(field_id)
    return match.group(1) if match else None


def _option_stem(option_value: str) -> str:
    for prefix in ("ja_", "nej_"):
        if option_value.startswith(prefix):
            return option_value[len(prefix) :]
    return option_value


def apply_checkbox_consistency_guard(page_response: dict, checkbox_fields: list) -> None:
    """Guard: if a checkbox's paired free-text sub-field (naming convention:
    shares the checkbox's question-number prefix and the option's stem
    appears in its id, e.g. `..._q11_annat_tillfalle_text` pairs with option
    `annat_tillfalle` on `..._q11_tillfalle`) has a value in this same
    response, ensure the parent option is included even if the model didn't
    select it. Mutates `page_response` in place."""
    for checkbox in checkbox_fields:
        prefix = _question_prefix(checkbox.field_id)
        if prefix is None:
            continue
        selected = page_response.get(checkbox.field_id)
        selected_list = list(selected) if isinstance(selected, list) else ([selected] if selected else [])
        for option_value, _label in checkbox.options:
            if option_value in selected_list:
                continue
            stem = _option_stem(option_value)
            has_paired_value = any(
                field_id != checkbox.field_id and _question_prefix(field_id) == prefix and stem in field_id and value
                for field_id, value in page_response.items()
            )
            if has_paired_value:
                selected_list.append(option_value)
        if selected_list:
            page_response[checkbox.field_id] = selected_list


def _apply_guards(raw_entries: list[dict], fields_on_page: list[FieldMatch], template_fields: dict) -> dict:
    fields_by_id = {f.field_id: f for f in fields_on_page}
    cleaned = {}
    for entry in raw_entries:
        field_id = entry.get("fieldId")
        match = fields_by_id.get(field_id)
        if match is None:
            continue  # guard: drop fieldIds not in this page's known field set

        value = entry.get("value")
        if match.options:
            value = remap_choice_value(value, match.options)

        template_field = template_fields.get(field_id)
        description = getattr(template_field, "description", None) if template_field else None
        if echoes_placeholder_example(value, description):
            continue

        cleaned[field_id] = value

    checkbox_fields = [f for f in fields_on_page if f.field_type == "checkbox"]
    apply_checkbox_consistency_guard(cleaned, checkbox_fields)
    return cleaned


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_vlm_fallback(
    pages: list[pymupdf.Pixmap],
    field_matches: list[FieldMatch],
    mark_results: dict[str, MarkResult],
    template_schema: FormTemplateSchema,
) -> dict[str, VlmResult]:
    escalated_by_page = _escalated_fields_by_page(field_matches, mark_results)
    if not escalated_by_page:
        return {}

    template_fields = _flatten_template_fields(template_schema)
    page_timeout = settings.OCR_VLM_PAGE_TIMEOUT_SECONDS
    form_budget = settings.OCR_VLM_FORM_TIMEOUT_SECONDS
    elapsed_seconds = 0.0

    results: dict[str, VlmResult] = {}
    try:
        for page_index, escalated_matches in escalated_by_page.items():
            if elapsed_seconds >= form_budget:
                break  # per-form ceiling hit -- stop escalating further pages, never raise

            fields_on_page = [m for m in field_matches if m.page_index == page_index]
            page_template_fields = [
                template_fields[m.field_id] for m in fields_on_page if m.field_id in template_fields
            ]
            prompt = _build_prompt(page_template_fields)
            image_b64 = _encode_page_for_vlm(pages[page_index])

            start = time.monotonic()
            try:
                raw = _call_ollama(prompt, image_b64, timeout=page_timeout)
            except SoftTimeLimitExceeded:
                # Celery's hard kill is imminent -- don't retry/continue to
                # another slow call, stop immediately (re-raise to the outer
                # handler below) so run_pipeline still has time to reach
                # merge/validation/save with whatever's accumulated (#51).
                raise
            except Exception:
                elapsed_seconds += time.monotonic() - start
                continue  # a failed/timed-out call leaves these fields unresolved for #50 to flag as failed
            elapsed_seconds += time.monotonic() - start

            cleaned = _apply_guards(raw.get("data", []), fields_on_page, template_fields)

            for match in escalated_matches:
                if match.field_id not in cleaned:
                    continue
                confidence = "low" if match.field_type == "text" else "high"
                results[match.field_id] = VlmResult(
                    field_id=match.field_id, value=cleaned[match.field_id], confidence=confidence
                )
    except SoftTimeLimitExceeded:
        # Whatever pages completed before the interrupt keep their real VLM
        # answers (`results` was populated incrementally above); fields on
        # pages not reached yet simply aren't in `results` -- merge.py (#50)
        # already falls back to their classic value, or flags them "failed"
        # if that's missing too, exactly like any other unresolved field.
        pass

    return results

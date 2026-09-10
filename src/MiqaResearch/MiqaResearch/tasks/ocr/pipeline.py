"""Orchestrates the full classic-OCR + VLM-fallback pipeline for one
PromData upload (docs/prom-ocr-handoff.md).

Every stage (#44/#47-#50) is real as of #50: field matching, mark detection,
VLM escalation, merge, and kpforms validation.
"""

import time
from dataclasses import dataclass, field

from django.conf import settings
from kpforms.helpers import get_form_by_template_id_and_version

from MiqaResearch.data.models import PromData

from . import field_matching, mark_detection, merge, preprocessing, validation, vlm_fallback

# Stages #46's harness treats as "classic path" for the <=2min/page acceptance bar --
# vlm_fallback is deliberately excluded, since it's exempt from that bar (#18 §4).
CLASSIC_PATH_STAGES = ("preprocessing", "field_matching", "mark_detection")


@dataclass
class PipelineResult:
    data: list[dict]
    fields_out_of_tolerance: list[str]
    extraction_flags: dict
    # Wall-clock seconds spent per named stage, keyed by the names used below --
    # lets a caller (the #46 evaluation harness) split classic-path latency from
    # the VLM fallback's separate budget without re-implementing this orchestration.
    stage_seconds: dict[str, float] = field(default_factory=dict)


def run_pipeline(prom_data: PromData) -> PipelineResult:
    stage_seconds: dict[str, float] = {}

    def timed(name, fn, *args):
        start = time.perf_counter()
        result = fn(*args)
        stage_seconds[name] = time.perf_counter() - start
        return result

    template_schema = timed(
        "get_template_schema", get_form_by_template_id_and_version, prom_data.prom_form_template.template_id
    )
    pages = timed("preprocessing", preprocessing.load_pages, prom_data)
    matches = timed("field_matching", field_matching.match_fields, pages, template_schema)
    # VLM-Only Mode (#62, docs/prom-ocr-handoff.md §10.2) skips mark_detection
    # entirely -- should_escalate is mode-forced to always fire regardless, so
    # its output would only be discarded.
    if settings.OCR_MODE == "vlm_only":
        mark_results = {}
    else:
        mark_results = timed("mark_detection", mark_detection.detect_marks, pages, matches)
    vlm_results = timed("vlm_fallback", vlm_fallback.run_vlm_fallback, pages, matches, mark_results, template_schema)
    data, extraction_flags = timed("merge", merge.merge_results, matches, mark_results, vlm_results)
    validated_data, fields_out_of_tolerance = timed("validation", validation.validate_submission, data, template_schema)

    return PipelineResult(
        data=validated_data,
        fields_out_of_tolerance=fields_out_of_tolerance,
        extraction_flags=extraction_flags,
        stage_seconds=stage_seconds,
    )

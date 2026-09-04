"""Orchestrates the full classic-OCR + VLM-fallback pipeline for one
PromData upload (docs/prom-ocr-handoff.md).

As of #44 this only wires the stages together end to end; #47-#50 fill in
the stage bodies with real logic. Until then every run produces an empty
(but schema-valid) result.
"""

from dataclasses import dataclass

from kpforms.helpers import get_form_by_template_id_and_version

from MiqaResearch.data.models import PromData

from . import field_matching, mark_detection, merge, preprocessing, validation, vlm_fallback


@dataclass
class PipelineResult:
    data: list[dict]
    fields_out_of_tolerance: list[str]
    extraction_flags: dict


def run_pipeline(prom_data: PromData) -> PipelineResult:
    template_schema = get_form_by_template_id_and_version(prom_data.prom_form_template.template_id)

    pages = preprocessing.load_pages(prom_data)
    matches = field_matching.match_fields(pages, template_schema)
    mark_results = mark_detection.detect_marks(pages, matches)
    vlm_results = vlm_fallback.run_vlm_fallback(pages, matches, mark_results, template_schema)
    data, extraction_flags = merge.merge_results(matches, mark_results, vlm_results)
    validated_data, fields_out_of_tolerance = validation.validate_submission(data, template_schema)

    return PipelineResult(
        data=validated_data,
        fields_out_of_tolerance=fields_out_of_tolerance,
        extraction_flags=extraction_flags,
    )

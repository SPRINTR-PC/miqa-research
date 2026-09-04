"""VLM escalation stage.

Per-field escalation trigger, batched into one VLM call per page that has at
least one escalated field, plus post-processing guards on the response
(#18). Stubbed out until #49.
"""

from dataclasses import dataclass

import pymupdf
from kpforms.form_schema import FormTemplateSchema

from .field_matching import FieldMatch
from .mark_detection import MarkResult


@dataclass
class VlmResult:
    field_id: str
    value: str | list[str] | None = None
    confidence: str = "low"


def run_vlm_fallback(
    pages: list[pymupdf.Pixmap],
    field_matches: list[FieldMatch],
    mark_results: dict[str, MarkResult],
    template_schema: FormTemplateSchema,
) -> dict[str, VlmResult]:
    """Stub for #49: escalates nothing, so no VLM-sourced values are produced."""
    return {}

"""Merge stage.

Combines classic-path and VLM-fallback results into kpforms-native
`data` entries plus `extraction_flags` provenance/confidence metadata
(#18 §5). Stubbed out until #50.
"""

from .field_matching import FieldMatch
from .mark_detection import MarkResult
from .vlm_fallback import VlmResult


def merge_results(
    field_matches: list[FieldMatch],
    mark_results: dict[str, MarkResult],
    vlm_results: dict[str, VlmResult],
) -> tuple[list[dict], dict]:
    """Stub for #50: emits no field values and no extraction_flags yet."""
    return [], {}

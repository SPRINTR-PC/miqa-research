"""Merge stage.

Combines classic-path and VLM-fallback results into kpforms-native `data`
entries plus `extraction_flags` provenance/confidence metadata (#18 §5).
"""

from .field_matching import MARK_FIELD_TYPES, FieldMatch
from .mark_detection import MarkResult
from .vlm_fallback import VlmResult, should_escalate


def _classic_value(match: FieldMatch, mark_result: MarkResult | None) -> str | list[str] | None:
    if match.field_type in MARK_FIELD_TYPES:
        return mark_result.value if mark_result is not None else None
    return match.text_value


def merge_results(
    field_matches: list[FieldMatch],
    mark_results: dict[str, MarkResult],
    vlm_results: dict[str, VlmResult],
) -> tuple[list[dict], dict]:
    """VLM fills only the fields flagged for escalation on that page -- it
    never overwrites a non-escalated field's classic-path value, since
    `vlm_results` only ever contains entries for fields vlm_fallback actually
    escalated (#18 §4). A field with neither a classic nor a VLM value gets
    no entry in kpforms' native `data` array (its schema has no `null` value
    -- see #11); `extraction_flags` is what makes a genuine double failure
    visible there, distinct from a field the paper form simply left blank.
    """
    data = []
    extraction_flags = {}

    for match in field_matches:
        mark_result = mark_results.get(match.field_id)
        vlm_result = vlm_results.get(match.field_id)
        escalated = should_escalate(match, mark_result)

        if vlm_result is not None:
            value = vlm_result.value
            source = "vlm"
            # Free text from the VLM is always low-confidence, even when it
            # clears the post-processing guards -- exact-match accuracy on
            # this type is too low to auto-accept (#18 §4[6]).
            confidence = "low" if match.field_type == "text" else vlm_result.confidence
        else:
            classic_value = _classic_value(match, mark_result)
            if classic_value is not None:
                value = classic_value
                source = "classic"
                confidence = "high"
            else:
                value = None
                source = "failed"
                confidence = None

        flag = {"source": source, "attempted": ["classic", "vlm"] if escalated else ["classic"]}
        if confidence is not None:
            flag["confidence"] = confidence
        extraction_flags[match.field_id] = flag

        if value is not None:
            data.append({"fieldId": match.field_id, "value": value})

    return data, extraction_flags

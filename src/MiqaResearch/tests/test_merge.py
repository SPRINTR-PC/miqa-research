from MiqaResearch.tasks.ocr.field_matching import FieldMatch
from MiqaResearch.tasks.ocr.mark_detection import MarkResult
from MiqaResearch.tasks.ocr.merge import merge_results
from MiqaResearch.tasks.ocr.vlm_fallback import VlmResult


def _match(
    field_id="f1",
    field_type="string",
    label_match_score=0.9,
    text_value=None,
    tesseract_word_confidence=90.0,
    options=None,
):
    return FieldMatch(
        field_id=field_id,
        field_type=field_type,
        page_index=0,
        label_match_score=label_match_score,
        text_value=text_value,
        tesseract_word_confidence=tesseract_word_confidence,
        options=options or [],
    )


def test_non_escalated_non_mark_field_uses_its_classic_text_value():
    match = _match(text_value="TD", tesseract_word_confidence=90.0)

    data, flags = merge_results([match], {}, {})

    assert data == [{"fieldId": "f1", "value": "TD"}]
    assert flags["f1"] == {"source": "classic", "attempted": ["classic"], "confidence": "high"}


def test_non_escalated_mark_field_uses_its_classic_mark_value():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A"), ("b", "B")])
    mark_result = MarkResult(field_id="f1", value="a", option_localization=1.0, mark_margin_ratio=2.0)

    data, flags = merge_results([match], {"f1": mark_result}, {})

    assert data == [{"fieldId": "f1", "value": "a"}]
    assert flags["f1"]["source"] == "classic"
    assert flags["f1"]["attempted"] == ["classic"]


def test_escalated_field_with_a_vlm_answer_is_authoritative():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A"), ("b", "B")])
    mark_result = MarkResult(field_id="f1", value="a", option_localization=0.5, mark_margin_ratio=1.0)
    vlm_result = VlmResult(field_id="f1", value="b", confidence="high")

    data, flags = merge_results([match], {"f1": mark_result}, {"f1": vlm_result})

    assert data == [{"fieldId": "f1", "value": "b"}]
    assert flags["f1"] == {"source": "vlm", "attempted": ["classic", "vlm"], "confidence": "high"}


def test_escalated_field_with_no_vlm_answer_falls_back_to_the_classic_value():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A"), ("b", "B")])
    mark_result = MarkResult(field_id="f1", value="a", option_localization=0.5, mark_margin_ratio=1.0)

    data, flags = merge_results([match], {"f1": mark_result}, {})

    assert data == [{"fieldId": "f1", "value": "a"}]
    assert flags["f1"]["source"] == "classic"
    assert flags["f1"]["attempted"] == ["classic", "vlm"]


def test_double_failure_omits_the_field_from_data_and_flags_it_as_failed():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A")])
    mark_result = MarkResult(field_id="f1", value=None, option_localization=0.0, mark_margin_ratio=0.0)

    data, flags = merge_results([match], {"f1": mark_result}, {})

    assert data == []
    assert flags["f1"] == {"source": "failed", "attempted": ["classic", "vlm"]}


def test_anchor_not_found_field_is_a_double_failure_with_no_classic_value():
    match = _match(label_match_score=0.1, text_value=None)

    data, flags = merge_results([match], {}, {})

    assert data == []
    assert flags["f1"]["source"] == "failed"
    assert flags["f1"]["attempted"] == ["classic", "vlm"]


def test_free_text_from_vlm_is_always_tagged_low_confidence():
    match = _match(field_type="text", label_match_score=0.9, tesseract_word_confidence=10.0)
    vlm_result = VlmResult(field_id="f1", value="ont i magen", confidence="high")

    _data, flags = merge_results([match], {}, {"f1": vlm_result})

    assert flags["f1"]["confidence"] == "low"


def test_checkbox_multiselect_value_is_a_list_in_the_merged_data():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A"), ("b", "B")])
    mark_result = MarkResult(field_id="f1", value=["a", "b"], option_localization=1.0, mark_margin_ratio=2.0)

    data, _flags = merge_results([match], {"f1": mark_result}, {})

    assert data == [{"fieldId": "f1", "value": ["a", "b"]}]


def test_every_field_gets_an_extraction_flags_entry_regardless_of_outcome():
    confident = _match(field_id="f1", text_value="TD")
    failed = _match(field_id="f2", label_match_score=0.1, text_value=None)

    _data, flags = merge_results([confident, failed], {}, {})

    assert set(flags) == {"f1", "f2"}

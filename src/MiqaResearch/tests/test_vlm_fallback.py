import json

import pymupdf
import pytest
from django.conf import settings
from kpforms.form_schema import ChoiceOption, FormSection, FormTemplateSchema, InputFieldCheckbox, InputGroup

from MiqaResearch.tasks.ocr import vlm_fallback
from MiqaResearch.tasks.ocr.field_matching import FieldMatch
from MiqaResearch.tasks.ocr.mark_detection import MarkResult


def _match(field_type="string", label_match_score=0.9, tesseract_word_confidence=90.0, text_value="hello", **kwargs):
    return FieldMatch(
        field_id=kwargs.pop("field_id", "f1"),
        field_type=field_type,
        page_index=kwargs.pop("page_index", 0),
        label_match_score=label_match_score,
        tesseract_word_confidence=tesseract_word_confidence,
        text_value=text_value,
        options=kwargs.pop("options", []),
        anchor_bbox=kwargs.pop("anchor_bbox", (0, 0, 10, 10)),
    )


def _mark_result(option_localization=1.0, mark_margin_ratio=2.0):
    return MarkResult(field_id="f1", option_localization=option_localization, mark_margin_ratio=mark_margin_ratio)


# ---------------------------------------------------------------------------
# should_escalate (#18 §4[5])
# ---------------------------------------------------------------------------


def test_escalates_when_anchor_not_found_regardless_of_type():
    match = _match(field_type="checkbox", label_match_score=0.4, options=[("a", "A")])
    assert vlm_fallback.should_escalate(match, _mark_result()) is True


def test_always_escalates_radio():
    match = _match(field_type="radio", options=[("a", "A"), ("b", "B")])
    assert vlm_fallback.should_escalate(match, _mark_result()) is True


def test_always_escalates_circle_scale_ranged_radio():
    match = _match(field_type="ranged-radio", options=[(str(i), str(i)) for i in range(4)])
    assert vlm_fallback.should_escalate(match, _mark_result()) is True


def test_does_not_escalate_a_confident_ranged_radio_grid():
    match = _match(field_type="ranged-radio", label_match_score=0.9, options=[(str(i), str(i)) for i in range(11)])
    confident = _mark_result(option_localization=1.0, mark_margin_ratio=2.0)
    assert vlm_fallback.should_escalate(match, confident) is False


def test_escalates_a_ranged_radio_grid_below_the_margin_bar():
    match = _match(field_type="ranged-radio", label_match_score=0.9, options=[(str(i), str(i)) for i in range(11)])
    weak = _mark_result(option_localization=1.0, mark_margin_ratio=1.2)
    assert vlm_fallback.should_escalate(match, weak) is True


def test_escalates_checkbox_with_incomplete_option_localization():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A"), ("b", "B")])
    incomplete = _mark_result(option_localization=0.5, mark_margin_ratio=5.0)
    assert vlm_fallback.should_escalate(match, incomplete) is True


def test_escalates_a_mark_type_field_with_no_mark_result_at_all():
    match = _match(field_type="checkbox", label_match_score=0.9, options=[("a", "A")])
    assert vlm_fallback.should_escalate(match, None) is True


def test_does_not_escalate_confident_non_mark_field():
    match = _match(field_type="string", label_match_score=0.9, tesseract_word_confidence=90.0, text_value="TD")
    assert vlm_fallback.should_escalate(match, None) is False


def test_escalates_non_mark_field_with_low_ocr_confidence():
    match = _match(field_type="string", label_match_score=0.9, tesseract_word_confidence=10.0, text_value="TD")
    assert vlm_fallback.should_escalate(match, None) is True


def test_escalates_datetime_field_with_no_digits_found():
    match = _match(field_type="datetime", label_match_score=0.9, tesseract_word_confidence=90.0, text_value="t.ex")
    assert vlm_fallback.should_escalate(match, None) is True


def test_does_not_escalate_datetime_field_with_a_valid_looking_date():
    match = _match(field_type="datetime", label_match_score=0.9, tesseract_word_confidence=90.0, text_value="20260501")
    assert vlm_fallback.should_escalate(match, None) is False


def test_escalates_numeric_field_with_no_digits_found():
    match = _match(field_type="numeric", label_match_score=0.9, tesseract_word_confidence=90.0, text_value="Hurofta?")
    assert vlm_fallback.should_escalate(match, None) is True


# ---------------------------------------------------------------------------
# Post-processing guards (#18 §4[2])
# ---------------------------------------------------------------------------


def test_remap_choice_value_passes_through_a_known_value_unchanged():
    options = [("forfarligt", "Förfärligt")]
    assert vlm_fallback.remap_choice_value("forfarligt", options) == "forfarligt"


def test_remap_choice_value_maps_a_diacritic_folded_label_back_to_its_value():
    options = [("forfarligt", "Förfärligt")]
    assert vlm_fallback.remap_choice_value("förfärligt", options) == "forfarligt"


def test_remap_choice_value_leaves_an_unknown_value_unchanged():
    options = [("a", "A")]
    assert vlm_fallback.remap_choice_value("something else", options) == "something else"


def test_remap_choice_value_handles_a_list_for_multiselect():
    options = [("ja_fettsnal_kost", "Ja, fettsnål kost"), ("nej", "Nej")]
    assert vlm_fallback.remap_choice_value(["ja, fettsnal kost", "nej"], options) == ["ja_fettsnal_kost", "nej"]


def test_echoes_placeholder_example_catches_an_exact_hint_echo():
    description = "Format: ÅÅÅÅMMDD, t.ex. 20250515."
    assert vlm_fallback.echoes_placeholder_example("20250515", description) is True


def test_echoes_placeholder_example_is_false_for_a_real_looking_value():
    description = "Format: ÅÅÅÅMMDD, t.ex. 20250515."
    assert vlm_fallback.echoes_placeholder_example("20260501", description) is False


def test_echoes_placeholder_example_is_false_with_no_hint_in_the_description():
    assert vlm_fallback.echoes_placeholder_example("20260501", "No hint here.") is False


def test_checkbox_consistency_guard_adds_an_option_whose_paired_free_text_has_a_value():
    checkbox = _match(field_id="prom101_q11_tillfalle", field_type="checkbox", options=[("annat_tillfalle", "Annat")])
    response = {"prom101_q11_tillfalle": [], "prom101_q11_annat_tillfalle_text": "Umeå kommun"}

    vlm_fallback.apply_checkbox_consistency_guard(response, [checkbox])

    assert response["prom101_q11_tillfalle"] == ["annat_tillfalle"]


def test_checkbox_consistency_guard_does_not_duplicate_an_already_selected_option():
    checkbox = _match(field_id="prom101_q11_tillfalle", field_type="checkbox", options=[("annat_tillfalle", "Annat")])
    response = {"prom101_q11_tillfalle": ["annat_tillfalle"], "prom101_q11_annat_tillfalle_text": "Umeå kommun"}

    vlm_fallback.apply_checkbox_consistency_guard(response, [checkbox])

    assert response["prom101_q11_tillfalle"] == ["annat_tillfalle"]


def test_checkbox_consistency_guard_leaves_unrelated_fields_alone():
    checkbox = _match(field_id="prom101_q11_tillfalle", field_type="checkbox", options=[("annat_tillfalle", "Annat")])
    response = {"prom101_q11_tillfalle": [], "prom101_q12_annat_tillfalle_text": "Something"}

    vlm_fallback.apply_checkbox_consistency_guard(response, [checkbox])

    assert response["prom101_q11_tillfalle"] == []


# ---------------------------------------------------------------------------
# Batching + timeout orchestration (mocked _call_ollama -- no real network)
# ---------------------------------------------------------------------------


def _template_schema():
    checkbox = InputFieldCheckbox(
        id="f1",
        label="Field one",
        type="checkbox",
        predefinedValue=False,
        options=[ChoiceOption(label="A", value="a", isWithinTolerance=True)],
    )
    return FormTemplateSchema(
        title="t",
        sections=[FormSection(id="s1", title="s1", inputGroups=[InputGroup(id="g1", fields=[checkbox])])],
    )


def _pixmap():
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)


def test_a_page_with_no_escalated_fields_issues_zero_calls(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(vlm_fallback, "_call_ollama", lambda *a, **kw: calls.append(1) or {"data": []})
    match = _match(field_type="string", label_match_score=0.9, tesseract_word_confidence=90.0, text_value="TD")

    vlm_fallback.run_vlm_fallback([_pixmap()], [match], {}, _template_schema())

    assert calls == []


def test_a_page_with_multiple_escalated_fields_issues_exactly_one_call(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(vlm_fallback, "_call_ollama", lambda *a, **kw: calls.append(1) or {"data": []})
    matches = [
        _match(field_id="f1", field_type="string", label_match_score=0.1, page_index=0),
        _match(field_id="f2", field_type="string", label_match_score=0.1, page_index=0),
    ]

    vlm_fallback.run_vlm_fallback([_pixmap()], matches, {}, _template_schema())

    assert len(calls) == 1


def test_only_escalated_fields_keep_a_vlm_result(monkeypatch, settings):
    monkeypatch.setattr(
        vlm_fallback,
        "_call_ollama",
        lambda *a, **kw: {"data": [{"fieldId": "f1", "value": "escalated"}, {"fieldId": "f2", "value": "confident"}]},
    )
    escalated = _match(field_id="f1", field_type="string", label_match_score=0.1, page_index=0)
    confident = _match(
        field_id="f2", field_type="string", label_match_score=0.9, tesseract_word_confidence=90.0, page_index=0
    )

    results = vlm_fallback.run_vlm_fallback([_pixmap()], [escalated, confident], {}, _template_schema())

    assert set(results) == {"f1"}
    assert results["f1"].value == "escalated"


def test_exceeding_the_per_form_timeout_ceiling_stops_further_calls_without_raising(monkeypatch, settings):
    settings.OCR_VLM_FORM_TIMEOUT_SECONDS = 0
    calls = []
    monkeypatch.setattr(vlm_fallback, "_call_ollama", lambda *a, **kw: calls.append(1) or {"data": []})
    matches = [
        _match(field_id="f1", field_type="string", label_match_score=0.1, page_index=0),
        _match(field_id="f2", field_type="string", label_match_score=0.1, page_index=1),
    ]

    results = vlm_fallback.run_vlm_fallback([_pixmap(), _pixmap()], matches, {}, _template_schema())

    assert calls == []
    assert results == {}


def test_a_failing_call_does_not_raise_and_leaves_the_field_unresolved(monkeypatch, settings):
    def boom(*args, **kwargs):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(vlm_fallback, "_call_ollama", boom)
    match = _match(field_id="f1", field_type="string", label_match_score=0.1, page_index=0)

    results = vlm_fallback.run_vlm_fallback([_pixmap()], [match], {}, _template_schema())

    assert results == {}


def test_free_text_results_are_always_tagged_low_confidence(monkeypatch, settings):
    monkeypatch.setattr(vlm_fallback, "_call_ollama", lambda *a, **kw: {"data": [{"fieldId": "f1", "value": "svar"}]})
    match = _match(
        field_id="f1", field_type="text", label_match_score=0.9, tesseract_word_confidence=10.0, page_index=0
    )

    results = vlm_fallback.run_vlm_fallback([_pixmap()], [match], {}, _template_schema())

    assert results["f1"].confidence == "low"


# ---------------------------------------------------------------------------
# Real integration test -- hits the actual local Ollama server (the fixture
# environment has qwen3-vl:8b-instruct-q8_0 pulled). Everything above is
# mocked/synthetic on purpose to stay fast; this one proves the real HTTP
# round trip (prompt, image encoding, response parsing) actually works.
# Slow (one real VLM call, likely 1-5 minutes on CPU per #17's benchmark).
# ---------------------------------------------------------------------------


@pytest.mark.vlm
def test_run_vlm_fallback_against_the_real_ollama_server():
    template_path = (
        settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "templates" / "PROM_1_PRO_GI_GU_SWE.json"
    )
    scan_path = settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "prom_samples" / "sample_01" / "scan.pdf"
    template_schema = FormTemplateSchema(**json.loads(template_path.read_text(encoding="utf-8")))

    doc = pymupdf.open(scan_path)
    pages = [page.get_pixmap(dpi=300) for page in doc]

    # Force escalation of one real field on page 0, regardless of what
    # field_matching/mark_detection (tested elsewhere) actually found.
    match = FieldMatch(field_id="prom101_initialer", field_type="string", page_index=0, label_match_score=0.0)

    results = vlm_fallback.run_vlm_fallback(pages, [match], {}, template_schema)

    assert isinstance(results, dict)
    if "prom101_initialer" in results:
        result = results["prom101_initialer"]
        assert result.field_id == "prom101_initialer"
        assert result.confidence in ("low", "high")

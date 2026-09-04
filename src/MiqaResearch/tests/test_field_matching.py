import json

import pymupdf
import pytest
from django.conf import settings
from kpforms.form_schema import FormTemplateSchema

from MiqaResearch.tasks.ocr import field_matching

FIXTURES_DIR = settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "prom_samples"
TEMPLATE_PATH = settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "templates" / "PROM_1_PRO_GI_GU_SWE.json"


def _word(text, left, top, right, bottom, conf=95.0, block=0, par=0, line=0):
    return {
        "text": text,
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "conf": conf,
        "block": block,
        "par": par,
        "line": line,
    }


# ---------------------------------------------------------------------------
# Fast unit tests against synthetic word lists -- no Tesseract/real fixtures.
# ---------------------------------------------------------------------------


def test_text_similarity_is_diacritic_tolerant():
    # Tesseract sometimes mangles å/ä/ö -- scoring both ways should recover this.
    assert field_matching._text_similarity("Använder Du blöja?", "Anvander Du bloja?") > 0.9


def test_text_similarity_treats_genuinely_different_text_as_dissimilar():
    assert field_matching._text_similarity("Använder Du blöja?", "Helt annan text") < 0.5


def test_best_window_match_finds_the_right_window_and_ignores_noise():
    words = [
        _word("Har", 0, 0, 30, 20),
        _word("Du", 35, 0, 55, 20),
        _word("ont", 60, 0, 90, 20),
        _word("i", 95, 0, 105, 20),
        _word("magen?", 110, 0, 170, 20),
        _word("[]", 200, 0, 220, 20),  # would be dropped at OCR-extraction time; kept here to prove it's harmless
    ]

    score, bbox = field_matching._best_window_match("Har Du ont i magen?", words)

    assert score > 0.9
    assert bbox == (0, 0, 170, 20)


def test_localize_field_anchors_finds_the_right_page_per_field():
    fields = [
        field_matching._FlatField(id="q1", label="Har Du ont i magen", type="string", order=0),
        field_matching._FlatField(id="q2", label="Kissar Du ofta pa natten", type="string", order=1),
    ]
    pages_words = [
        [_word(w, i * 40, 0, i * 40 + 35, 20) for i, w in enumerate(["Har", "Du", "ont", "i", "magen"])],
        [_word(w, i * 40, 0, i * 40 + 35, 20) for i, w in enumerate(["Kissar", "Du", "ofta", "pa", "natten"])],
    ]

    anchors = field_matching._localize_field_anchors(fields, pages_words)

    assert anchors["q1"][1] == 0  # page_idx
    assert anchors["q2"][1] == 1


def test_compute_field_regions_carves_from_anchor_bottom_to_next_anchor_top():
    fields = [
        field_matching._FlatField(id="q1", label="a", type="string", order=0),
        field_matching._FlatField(id="q2", label="b", type="string", order=1),
    ]
    anchors = {
        "q1": (1.0, 0, (0, 0, 50, 20)),
        "q2": (1.0, 0, (0, 100, 50, 120)),
    }

    regions = field_matching._compute_field_regions(fields, anchors, page_heights=[500])

    assert regions["q1"] == (0, 20, 100)
    assert regions["q2"] == (0, 120, 500)


def test_compute_field_regions_falls_back_to_minimum_height_on_overlap():
    """A multi-line-wrapped label's own bbox can extend past where the next
    field's anchor starts -- two real spans crossing, not a bug in either."""
    fields = [
        field_matching._FlatField(id="q1", label="a", type="string", order=0),
        field_matching._FlatField(id="q2", label="b", type="string", order=1),
    ]
    anchors = {
        "q1": (1.0, 0, (0, 0, 50, 200)),  # bottom (200) is past q2's own top (50)
        "q2": (1.0, 0, (0, 40, 50, 60)),
    }

    regions = field_matching._compute_field_regions(fields, anchors, page_heights=[500])

    assert regions["q1"] == (0, 200, 200 + field_matching.REGION_MIN_HEIGHT)


def test_extract_text_value_joins_words_and_averages_confidence():
    words = [_word("ont", 0, 0, 30, 20, conf=90.0), _word("i", 35, 0, 45, 20, conf=80.0)]

    text, confidence = field_matching._extract_text_value(words)

    assert text == "ont i"
    assert confidence == pytest.approx(85.0)


def test_extract_text_value_is_none_for_an_empty_region():
    assert field_matching._extract_text_value([]) == (None, 0.0)


def test_flatten_template_preserves_document_order():
    template_schema = FormTemplateSchema(**json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")))

    fields = field_matching._flatten_template(template_schema)

    assert [f.order for f in fields] == list(range(len(fields)))
    assert fields[0].id == "prom101_studie_id"


# ---------------------------------------------------------------------------
# Real Tesseract OCR against the actual fixture set -- slow (real OCR over all
# 10 samples), but this is exactly what the acceptance criteria ask to verify.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def matches_by_sample():
    template_schema = FormTemplateSchema(**json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")))
    results = {}
    for sample_dir in sorted(FIXTURES_DIR.glob("sample_*")):
        doc = pymupdf.open(sample_dir / "scan.pdf")
        pages = [page.get_pixmap(dpi=300) for page in doc]
        results[sample_dir.name] = field_matching.match_fields(pages, template_schema)
    return results


def test_label_localization_hit_rate_approaches_16s_measured_96_percent(matches_by_sample):
    all_matches = [m for matches in matches_by_sample.values() for m in matches]
    hits = sum(1 for m in all_matches if m.label_match_score >= field_matching.MIN_ANCHOR_SCORE)

    # #16 measured 96.2% (356/370) with its (unported) box-discovery half still
    # attached; this only ports the label-localization half, so a close approach
    # -- not an exact reproduction -- is the bar.
    assert len(all_matches) == 370  # 37 fields/template x 10 samples
    assert hits / len(all_matches) >= 0.90


def test_sample_09s_swapped_pages_resolve_with_no_page_order_special_casing(matches_by_sample):
    """sample_09 has physical pages 3/4 swapped relative to every other sample
    (a realistic scanning artifact, #16). Searching all pages per field, rather
    than trusting a fixed index, should recover this with zero special-casing."""

    def page_of(sample_id, field_id):
        matches = {m.field_id: m for m in matches_by_sample[sample_id]}
        return matches[field_id].page_index

    # q12 belongs to the "Besvara frågor (12-16)" section, q17 to "Vattenkastningsbesvär
    # (17-25)" -- swapped in sample_09 (manifest: page 3 has Vattenkastningsbesvär,
    # page 4 has Besvara frågor), unswapped in every other sample.
    q12, q17 = "prom101_q12_anvander_bloja", "prom101_q17_urinera_ofta_dagen"
    assert page_of("sample_09", q12) == page_of("sample_01", q17)
    assert page_of("sample_09", q17) == page_of("sample_01", q12)
    assert page_of("sample_09", q12) != page_of("sample_01", q12)


def test_non_mark_fields_get_a_plausible_bounded_text_value(matches_by_sample):
    non_mark_matches = [
        m
        for matches in matches_by_sample.values()
        for m in matches
        if m.field_type not in field_matching.MARK_FIELD_TYPES
    ]

    with_a_value = [m for m in non_mark_matches if m.text_value]
    # Not every non-mark field anchors confidently enough to get a region, but
    # most should on real fixtures -- and none should run away into an
    # unbounded, multi-field blob (the failure mode fixed by capping the
    # extraction window well below a full carved region).
    assert len(with_a_value) / len(non_mark_matches) >= 0.7
    assert all(len(m.text_value) < 250 for m in with_a_value)


def test_mark_type_fields_get_no_text_value_from_this_stage(matches_by_sample):
    mark_matches = [
        m for matches in matches_by_sample.values() for m in matches if m.field_type in field_matching.MARK_FIELD_TYPES
    ]

    assert mark_matches  # sanity: the fixture set does have mark-type fields
    assert all(m.text_value is None for m in mark_matches)

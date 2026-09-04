import io
import json

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from MiqaResearch.data.management.commands.evaluate_prom_ocr import DEFAULT_FIXTURES_DIR, normalize_value, score_sample
from MiqaResearch.tasks.ocr import vlm_fallback

FIXTURES_DIR = settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "prom_samples"


def test_normalize_value_applies_nfkc_and_casefold():
    assert normalize_value("Förfärligt") == normalize_value("förfärligt")
    assert normalize_value("ABC") == normalize_value("abc")


def test_normalize_value_compares_multiselect_lists_as_a_set_regardless_of_order():
    assert normalize_value(["Ja", "Nej"]) == normalize_value(["nej", "JA"])
    assert normalize_value(["Ja"]) != normalize_value(["Ja", "Nej"])


def test_score_sample_counts_exact_matches_after_normalization():
    ground_truth = [{"fieldId": "q1", "value": "5"}, {"fieldId": "q2", "value": ["a", "b"]}]
    predicted = [{"fieldId": "q1", "value": "5"}, {"fieldId": "q2", "value": ["B", "A"]}]

    assert score_sample(ground_truth, predicted) == (2, 2)


def test_score_sample_counts_missing_or_wrong_values_against_the_ground_truth_total():
    ground_truth = [{"fieldId": "q1", "value": "5"}, {"fieldId": "q2", "value": "no"}]
    predicted = [{"fieldId": "q1", "value": "wrong"}]

    assert score_sample(ground_truth, predicted) == (0, 2)


def test_ground_truth_field_counts_match_17s_reported_325_across_all_samples():
    """Spot-check against #17's own reported denominator (325 ground-truth fields
    across all 10 samples), per #46's acceptance criteria."""
    total = sum(
        len(json.loads((sample_dir / "ground_truth.json").read_text(encoding="utf-8"))["data"])
        for sample_dir in sorted(FIXTURES_DIR.glob("sample_*"))
    )

    assert total == 325


@pytest.mark.django_db
def test_evaluate_prom_ocr_runs_all_ten_fixtures_and_reports_classic_path_only_accuracy(monkeypatch):
    # Real field_matching/mark_detection/merge (#47/#48/#50) run for real
    # here -- that's the point, exercising the actual classic path. VLM calls
    # are mocked out: #49's own tests cover VLM behavior, and a real call
    # here would just be an expensive, redundant round trip.
    monkeypatch.setattr(vlm_fallback, "run_vlm_fallback", lambda *args, **kwargs: {})
    out = io.StringIO()

    with pytest.raises(CommandError, match="accuracy"):
        call_command("evaluate_prom_ocr", stdout=out)

    report = out.getvalue()
    assert report.count("sample_") == 10
    assert "overall" in report

    overall_line = next(line for line in report.splitlines() if line.startswith("overall"))
    accuracy = int(overall_line.split()[1].split("/")[0]) / int(overall_line.split()[1].split("/")[1])
    # Classic path alone (per #47/#48's own measured numbers) is genuinely
    # non-trivial but nowhere near the 95% bar -- that gap is exactly why the
    # VLM fallback (#49) exists.
    assert 0.05 <= accuracy < 0.95


@pytest.mark.django_db
def test_evaluate_prom_ocr_fixtures_dir_argument_rejects_a_directory_with_no_samples(tmp_path):
    with pytest.raises(CommandError, match="No sample_"):
        call_command("evaluate_prom_ocr", fixtures_dir=str(tmp_path))


def test_default_fixtures_dir_points_at_the_real_sample_directory():
    assert DEFAULT_FIXTURES_DIR == FIXTURES_DIR

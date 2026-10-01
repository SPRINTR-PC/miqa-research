"""Startup system check for missing manual builds."""

from pathlib import Path

from django.core.checks import run_checks

FIXTURE_BUILD_DIR = Path(__file__).resolve().parent / "fixtures" / "manuals"


def _manual_warnings():
    return [m for m in run_checks() if m.id.startswith("documentation.")]


def test_no_warning_when_every_manual_has_an_english_build(settings):
    settings.MANUALS_BUILD_DIR = FIXTURE_BUILD_DIR

    assert _manual_warnings() == []


def test_warns_about_each_manual_without_an_english_build(settings, tmp_path):
    (tmp_path / "user" / "en").mkdir(parents=True)
    (tmp_path / "user" / "en" / "index.fjson").write_text("{}")
    settings.MANUALS_BUILD_DIR = tmp_path

    warnings = _manual_warnings()

    assert [w.id for w in warnings] == ["documentation.W001"]
    assert "Technical Manual" in warnings[0].msg

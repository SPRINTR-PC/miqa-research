import uuid

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from kpforms.models import FormSubmission

from MiqaResearch.data.management.commands.import_prom_form_template import DEFAULT_TEMPLATE_NAME
from MiqaResearch.data.models import ParsedPromForm, PromData, PromFormTemplate, ResearchProject
from MiqaResearch.tasks.ocr import mark_detection, run_ocr_on_prom_data, vlm_fallback

User = get_user_model()

SAMPLE_SCAN_PATH = (
    settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "prom_samples" / "sample_01" / "scan.pdf"
)


@pytest.fixture
def prom_data(db, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path

    call_command("import_prom_form_template")
    template = PromFormTemplate.objects.get(name=DEFAULT_TEMPLATE_NAME)
    project = ResearchProject.objects.create(name="Test project", description="Test project for OCR pipeline tests")
    user = User.objects.create_user(username="uploader", email="uploader@example.com", password="password")

    return PromData.objects.create(
        project=project,
        prom_form_template=template,
        prom_form_file=SimpleUploadedFile("scan.pdf", SAMPLE_SCAN_PATH.read_bytes(), content_type="application/pdf"),
        uploaded_by=user,
    )


@pytest.mark.django_db
def test_run_ocr_on_prom_data_stores_a_schema_valid_parsed_prom_form(prom_data, monkeypatch):
    # Real field_matching/mark_detection/merge (#47/#48/#50) run for real
    # here. VLM calls are mocked out: #49's own tests cover VLM behavior, and
    # a real call here would just be an expensive, redundant round trip.
    monkeypatch.setattr(vlm_fallback, "run_vlm_fallback", lambda *args, **kwargs: {})

    run_ocr_on_prom_data(prom_data.id)

    parsed = ParsedPromForm.objects.get(prom_file=prom_data)
    assert isinstance(parsed.data["data"], list)
    assert isinstance(parsed.data["fieldsOutOfTolerance"], list)
    # Every template field gets a provenance entry, whether or not it produced a value.
    assert len(parsed.extraction_flags) == 37
    assert all(flag["source"] in ("classic", "vlm", "failed") for flag in parsed.extraction_flags.values())
    # Every field actually in the merged data has a real, non-null value.
    assert all(entry["value"] is not None for entry in parsed.data["data"])


@pytest.mark.django_db
def test_a_soft_time_limit_mid_escalation_still_saves_a_parsed_prom_form(prom_data, monkeypatch):
    """sample_01 (#48/#49's own measurements) escalates fields across
    multiple pages -- real field_matching/mark_detection run for real here,
    and _call_ollama (not run_vlm_fallback) is mocked so vlm_fallback's own
    per-page loop and its SoftTimeLimitExceeded handling (#51) actually run."""
    calls = []

    def flaky_call_ollama(prompt, image_b64, timeout):
        calls.append(1)
        if len(calls) == 1:
            return {"data": []}
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(vlm_fallback, "_call_ollama", flaky_call_ollama)

    run_ocr_on_prom_data(prom_data.id)  # must not raise

    assert len(calls) >= 2  # proves the interrupt fired mid-loop, after at least one page completed
    parsed = ParsedPromForm.objects.get(prom_file=prom_data)
    assert isinstance(parsed.data["data"], list)
    assert len(parsed.extraction_flags) == 37
    assert all(flag["source"] in ("classic", "vlm", "failed") for flag in parsed.extraction_flags.values())
    assert all(entry["value"] is not None for entry in parsed.data["data"])


@pytest.mark.django_db
def test_vlm_only_mode_skips_mark_detection_and_stores_a_valid_parsed_prom_form(prom_data, monkeypatch, settings):
    # #67, docs/prom-ocr-handoff.md §10.2 -- VLM-Only Mode skips mark_detection
    # entirely and forces every field to escalate. Real field_matching runs for
    # real here; mark_detection is asserted un-called rather than mocked-and-discarded,
    # and _call_ollama (not run_vlm_fallback) is mocked so should_escalate's mode
    # branch actually drives real escalation-gated batching.
    settings.OCR_MODE = "vlm_only"

    def unexpected_call(*args, **kwargs):
        raise AssertionError("mark_detection.detect_marks must not be called in VLM-Only Mode")

    monkeypatch.setattr(mark_detection, "detect_marks", unexpected_call)
    monkeypatch.setattr(vlm_fallback, "_call_ollama", lambda *args, **kwargs: {"data": []})

    run_ocr_on_prom_data(prom_data.id)

    parsed = ParsedPromForm.objects.get(prom_file=prom_data)
    assert isinstance(parsed.data["data"], list)
    assert len(parsed.extraction_flags) == 37
    # Every field was escalated (attempted VLM), even mark-type fields that
    # Hybrid Mode's own mark_detection would otherwise have resolved classically.
    assert all("vlm" in flag["attempted"] for flag in parsed.extraction_flags.values())


@pytest.mark.django_db
def test_run_ocr_on_prom_data_never_creates_a_kpforms_form_submission(prom_data, monkeypatch):
    monkeypatch.setattr(vlm_fallback, "run_vlm_fallback", lambda *args, **kwargs: {})

    run_ocr_on_prom_data(prom_data.id)

    # OCR output is a machine-drafted candidate reading, not a real patient
    # submission -- validation.py calls kpforms' validator directly and never
    # goes through submit_form_data (#11/#13/#50).
    assert not FormSubmission.objects.exists()


@pytest.mark.django_db
def test_running_ocr_twice_appends_a_new_parsed_prom_form_row_rather_than_overwriting(prom_data, monkeypatch):
    monkeypatch.setattr(vlm_fallback, "run_vlm_fallback", lambda *args, **kwargs: {})

    run_ocr_on_prom_data(prom_data.id)
    first = ParsedPromForm.objects.get(prom_file=prom_data)

    run_ocr_on_prom_data(prom_data.id)

    rows = ParsedPromForm.objects.filter(prom_file=prom_data)
    assert rows.count() == 2
    assert first in rows  # the original row is untouched, not upserted


@pytest.mark.django_db
def test_run_ocr_on_prom_data_is_a_noop_for_a_missing_prom_data():
    run_ocr_on_prom_data(uuid.uuid4())

    assert not ParsedPromForm.objects.exists()

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from MiqaResearch.data.management.commands.import_prom_form_template import DEFAULT_TEMPLATE_NAME
from MiqaResearch.data.models import ParsedPromForm, PromData, PromFormTemplate, ResearchProject
from MiqaResearch.tasks.ocr import run_ocr_on_prom_data, vlm_fallback

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
    # Real field_matching/mark_detection (#47/#48) run for real here. VLM
    # calls are mocked out: merge.py is still a stub (#50), so any escalated
    # field's real VLM answer would be computed only to be discarded -- an
    # expensive no-op once vlm_fallback (#49) stopped being a free stub.
    monkeypatch.setattr(vlm_fallback, "run_vlm_fallback", lambda *args, **kwargs: {})

    run_ocr_on_prom_data(prom_data.id)

    parsed = ParsedPromForm.objects.get(prom_file=prom_data)
    # merge.py (#50) is still a stub, so no field values reach the final output yet.
    assert parsed.data == {"data": [], "fieldsOutOfTolerance": []}


@pytest.mark.django_db
def test_run_ocr_on_prom_data_is_a_noop_for_a_missing_prom_data():
    run_ocr_on_prom_data(uuid.uuid4())

    assert not ParsedPromForm.objects.exists()

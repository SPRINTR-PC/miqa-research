"""Unit test for the Celery task wrapper around DICOM ingestion (#126).

Calls the task's underlying function directly (`.func(...)`), bypassing
dispatch -- this thin wrapper's only job is id-resolution and counts
extraction, so a plain unit test is enough here; real dispatch is exercised
only by the concurrency scenario in test_dicom_ingestion_performance.py, per
#116's Testing Decisions.
"""
import pytest

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.tasks import ingest_dicom_source
from tests.dicom_fixtures import build_ct_image, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Task wrapper project", description="Project for #126 tests")


def test_ingest_dicom_source_ingests_the_file_and_returns_counts(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    counts = ingest_dicom_source.func(str(research_project.id), str(src))

    assert counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 1


def test_ingest_dicom_source_raises_for_unknown_research_project(db):
    with pytest.raises(ResearchProject.DoesNotExist):
        ingest_dicom_source.func("00000000-0000-0000-0000-000000000000", "s3://irrelevant/prefix")

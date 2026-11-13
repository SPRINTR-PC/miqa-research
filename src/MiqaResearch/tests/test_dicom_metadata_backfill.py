"""Backfill: re-sanitize existing `DicomFile.metadata` from the stored files (#273).

Seam: the `resanitize_dicom_metadata` task (run synchronously via `.call()`).
"""
import pytest

from MiqaResearch.data.models import DicomFile, ResearchProject, StudyParticipant
from MiqaResearch.tasks.dicom_handling.metadata_backfill import resanitize_dicom_metadata
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom
from tests.dicom_ingest_helper import ingest_files

LEGACY_DUMP = {"PatientBirthDate": "19750131", "AccessionNumber": "ACC-1", "KVP": 120.0}


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def storage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Backfill project", description="#273")


def _ingest(research_project, tmp_path, ds, name):
    report = ingest_files(research_project, write_dicom(ds, tmp_path / name))
    assert report.counts["ingested"] == 1
    return DicomFile.objects.get(sop_instance_uid=report.results[0].sop_instance_uid)


def test_backfill_replaces_legacy_dumps_with_the_profile_dump(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_ct_image(), "ct.dcm")
    expected = dcm_file.metadata
    DicomFile.objects.filter(pk=dcm_file.pk).update(metadata=LEGACY_DUMP)

    result = resanitize_dicom_metadata.call()

    dcm_file.refresh_from_db()
    assert dcm_file.metadata == expected
    assert dcm_file.metadata["PatientName"] == StudyParticipant.objects.get().alias1
    assert "19750131" not in str(dcm_file.metadata)
    assert result == {"updated": 1, "unchanged": 0, "errors": 0}


def test_backfill_tolerates_an_unlinked_study(research_project, tmp_path):
    """ADR 0035 (#415): an unlinked Study is re-sanitized under a key-derived pseudonym, never the PatientID."""
    dcm_file = _ingest(research_project, tmp_path, build_ct_image(), "ct.dcm")
    key = dcm_file.series.study.participant_key
    key.study_participant = None
    key.save(update_fields=["study_participant"])
    DicomFile.objects.filter(pk=dcm_file.pk).update(metadata=LEGACY_DUMP)

    result = resanitize_dicom_metadata.call()

    dcm_file.refresh_from_db()
    assert result == {"updated": 1, "unchanged": 0, "errors": 0}
    assert dcm_file.metadata["PatientName"].startswith("UNLINKED-")


def test_backfill_is_idempotent(research_project, tmp_path):
    _ingest(research_project, tmp_path, build_ct_image(), "ct.dcm")
    DicomFile.objects.update(metadata=LEGACY_DUMP)
    resanitize_dicom_metadata.call()
    after_first = DicomFile.objects.get().metadata

    result = resanitize_dicom_metadata.call()

    assert DicomFile.objects.get().metadata == after_first
    assert result == {"updated": 0, "unchanged": 1, "errors": 0}


def test_backfill_keeps_extractor_summaries(research_project, tmp_path):
    _ingest(research_project, tmp_path, build_wsi(), "wsi.dcm")
    expected_summary = DicomFile.objects.get().metadata["pathology_summary"]
    DicomFile.objects.update(metadata=LEGACY_DUMP)

    resanitize_dicom_metadata.call()

    assert DicomFile.objects.get().metadata["pathology_summary"] == expected_summary


def test_unreadable_file_is_counted_and_others_continue(research_project, tmp_path):
    broken = _ingest(research_project, tmp_path, build_ct_image(), "ct1.dcm")
    _ingest(research_project, tmp_path, build_ct_image(sop_instance_uid="1.2.9999.42.1.2003"), "ct2.dcm")
    DicomFile.objects.update(metadata=LEGACY_DUMP)
    broken.file.storage.delete(broken.file.name)

    result = resanitize_dicom_metadata.call()

    assert result == {"updated": 1, "unchanged": 0, "errors": 1}
    broken.refresh_from_db()
    assert broken.metadata == LEGACY_DUMP

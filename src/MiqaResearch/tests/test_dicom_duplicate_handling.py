"""Repeated-ingestion duplicate handling (#120, #109 decisions).

A run re-encountering a file whose (pseudonymized) SOP Instance UID already
exists distinguishes:
- an ordinary no-op duplicate (content identical to what's stored) →
  `skipped_duplicate`, in either duplicate-handling mode;
- a duplicate whose content actually differs from what's stored →
  `duplicate_conflict`, always reported distinctly; in `update` mode the
  stored record is replaced in place, in `skip` mode nothing is written.

The project's standing default is `ResearchProject.dicom_duplicate_handling`
(skip/update, default skip); a single run overrides it via
`run_ingestion(..., overwrite_existing=...)`.
"""
import hashlib

import pytest

from MiqaResearch.data.models import DicomFile, DicomSeries, DicomStudy, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import DEFAULT_PATIENT_ID, build_ct_image, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Ingestion duplicates project", description="Project for #120 duplicate tests")


@pytest.fixture
def same_sop_pair(tmp_path):
    """(original, re-scan) bytes: same UIDs/PatientID, different file content."""
    ds = build_ct_image()
    original = write_dicom(ds, tmp_path / "first.dcm").read_bytes()
    ds_rescan = build_ct_image()
    ds_rescan.KVP = "140"  # same SOP Instance UID, different content
    rescan = write_dicom(ds_rescan, tmp_path / "rescan.dcm").read_bytes()
    assert original != rescan
    return original, rescan


# --- Content identity -----------------------------------------------------------


def test_stored_file_carries_content_hash(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    raw = src.read_bytes()

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    assert DicomFile.objects.get().content_sha256 == hashlib.sha256(raw).hexdigest()


def test_rerun_of_identical_file_is_noop_duplicate_skip_mode(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    run_ingestion(research_project, src)
    stored_before = DicomFile.objects.get().file.read()

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 1, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 1
    DicomFile.objects.get().file.seek(0)
    assert DicomFile.objects.get().file.read() == stored_before


def test_rerun_of_identical_file_is_noop_duplicate_update_mode(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    research_project.dicom_duplicate_handling = "update"
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    run_ingestion(research_project, src)

    report = run_ingestion(research_project, src)

    # Nothing changed -> ordinary no-op duplicate, not a conflict
    assert report.counts == {"ingested": 0, "skipped_duplicate": 1, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 1


# --- Conflicting duplicates -------------------------------------------------------


def test_conflicting_duplicate_is_distinct_outcome_skip_mode_writes_nothing(research_project, tmp_path, settings, same_sop_pair):
    settings.MEDIA_ROOT = tmp_path / "media"
    original, rescan = same_sop_pair
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    src.write_bytes(original)
    run_ingestion(research_project, src)
    dcm_file = DicomFile.objects.get()
    metadata_before = dcm_file.metadata
    dcm_file.file.seek(0)
    stored_before = dcm_file.file.read()

    rescan_path = tmp_path / "rescan.dcm"
    rescan_path.write_bytes(rescan)
    report = run_ingestion(research_project, rescan_path)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 1, "error": 0}
    assert report.results[0].outcome == "duplicate_conflict"
    assert DicomFile.objects.count() == 1
    # Skip mode: the stored record is untouched
    dcm_file.refresh_from_db()
    assert dcm_file.metadata == metadata_before
    dcm_file.file.seek(0)
    assert dcm_file.file.read() == stored_before


def test_conflicting_duplicate_update_mode_replaces_record_in_place(research_project, tmp_path, settings, same_sop_pair):
    settings.MEDIA_ROOT = tmp_path / "media"
    research_project.dicom_duplicate_handling = "update"
    original, rescan = same_sop_pair
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    src.write_bytes(original)
    first = run_ingestion(research_project, src)
    assert first.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    assert dcm_file.metadata["KVP"] == 120.0

    rescan_path = tmp_path / "rescan.dcm"
    rescan_path.write_bytes(rescan)
    report = run_ingestion(research_project, rescan_path)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 1, "error": 0}
    assert DicomFile.objects.count() == 1
    dcm_file.refresh_from_db()
    # File-level data replaced in place
    assert dcm_file.metadata["KVP"] == 140.0
    dcm_file.file.seek(0)
    assert dcm_file.file.read() == rescan
    assert dcm_file.content_sha256 == hashlib.sha256(rescan).hexdigest()
    # The series' size aggregate reflects the current file, not a double count
    series = dcm_file.series
    assert abs(series.file_size_in_mb - len(rescan) / (1024 * 1024)) < 1e-9


def test_update_mode_never_overwrites_populated_study_series_fields(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    research_project.dicom_duplicate_handling = "update"
    ds = build_ct_image(series_description="PHASE_1")
    src = write_dicom(ds, tmp_path / "a.dcm")
    run_ingestion(research_project, src)
    series = DicomSeries.objects.get()
    assert series.series_description == "PHASE_1"

    # Same SOP Instance UID, different content AND a disagreeing series description
    ds2 = build_ct_image(series_description="REPROCESS")
    ds2.KVP = "150"
    rescan = write_dicom(ds2, tmp_path / "b.dcm")
    report = run_ingestion(research_project, rescan)

    assert report.counts["duplicate_conflict"] == 1
    series.refresh_from_db()
    assert series.series_description == "PHASE_1"  # fill-blank-only, never overwritten
    assert DicomStudy.objects.count() == 1
    assert DicomSeries.objects.count() == 1


# --- Per-run override of the project setting ---------------------------------------


def test_per_run_override_forces_update_on_skip_project(research_project, tmp_path, settings, same_sop_pair):
    settings.MEDIA_ROOT = tmp_path / "media"
    assert research_project.dicom_duplicate_handling == "skip"
    original, rescan = same_sop_pair
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    src.write_bytes(original)
    run_ingestion(research_project, src)

    rescan_path = tmp_path / "rescan.dcm"
    rescan_path.write_bytes(rescan)
    report = run_ingestion(research_project, rescan_path, overwrite_existing=True)

    assert report.counts["duplicate_conflict"] == 1
    dcm_file = DicomFile.objects.get()
    assert dcm_file.metadata["KVP"] == 140.0
    # The project's standing setting is unchanged
    research_project.refresh_from_db()
    assert research_project.dicom_duplicate_handling == "skip"


def test_per_run_override_forces_skip_on_update_project(research_project, tmp_path, settings, same_sop_pair):
    settings.MEDIA_ROOT = tmp_path / "media"
    research_project.dicom_duplicate_handling = "update"
    original, rescan = same_sop_pair
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    src.write_bytes(original)
    run_ingestion(research_project, src)

    rescan_path = tmp_path / "rescan.dcm"
    rescan_path.write_bytes(rescan)
    report = run_ingestion(research_project, rescan_path, overwrite_existing=False)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 1, "error": 0}
    dcm_file = DicomFile.objects.get()
    assert dcm_file.metadata["KVP"] == 120.0  # untouched


# --- Legacy records without a stored hash -------------------------------------------


def test_legacy_record_without_hash_falls_back_to_stored_bytes_comparison(research_project, tmp_path, settings, same_sop_pair):
    settings.MEDIA_ROOT = tmp_path / "media"
    original, _ = same_sop_pair
    src = write_dicom(build_ct_image(), tmp_path / "a.dcm")
    src.write_bytes(original)
    run_ingestion(research_project, src)
    # Simulate a record created before content hashes were stored
    DicomFile.objects.update(content_sha256="")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 1, "duplicate_conflict": 0, "error": 0}

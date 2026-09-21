"""Multi-source DICOM ingestion (#120) — discovery across folder and S3 sources,
source validation, and the run's per-file behaviour for files found under a
source. Per the #98 testing decisions: tests call the top-level `run_ingestion`
seam directly and assert on what ends up in the database and what the run's
report says, never on internal stage call sequences.

S3 sources are exercised against moto (in-memory S3) through the same
boto3-based discovery client a real deployment would use.
"""
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from MiqaResearch.data.models import DicomFile, DicomStudy, ResearchProject
from MiqaResearch.tasks.dicom_handling.discovery import (
    S3SourceError,
    SourceInaccessibleError,
    SourceNotAllowedError,
    SourceNotFoundError,
)
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, write_dicom

STUDY_UIDS = {
    "a": ("1.2.9999.42.1.1001", "1.2.9999.42.1.1002", "1.2.9999.42.1.1003"),
    "b": ("1.2.9999.42.1.2001", "1.2.9999.42.1.2002", "1.2.9999.42.1.2003"),
    "c": ("1.2.9999.42.1.3001", "1.2.9999.42.1.3002", "1.2.9999.42.1.3003"),
}


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    """Default-deny allow-list that covers this test's tmp_path only."""
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Ingestion discovery project", description="Project for #120 tests")


def _write_ct(tag: str, path, sop_suffix: str) -> None:
    study_uid, series_uid, sop_uid = STUDY_UIDS[tag]
    ds = build_ct_image(
        study_instance_uid=study_uid,
        series_instance_uid=series_uid,
        sop_instance_uid=f"{sop_uid}{sop_suffix}",
        patient_id=f"P-{tag.upper()}",
    )
    write_dicom(ds, path)


# --- Folder discovery ---------------------------------------------------------


def test_folder_with_nested_subdirectories_ingests_every_dicom_file(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "export"
    (src / "series_a" / "slices").mkdir(parents=True)
    (src / "series_b" / "deep" / "nested").mkdir(parents=True)
    _write_ct("a", src / "top.dcm", "")
    _write_ct("b", src / "series_a" / "slices" / "a1.dcm", "")
    _write_ct("c", src / "series_b" / "deep" / "nested" / "c1.dcm", "")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 3, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert len(report.results) == 3
    assert DicomFile.objects.count() == 3
    assert DicomStudy.objects.count() == 3
    # Each file ingested with the single-file behaviour (own study/series/file)
    for dcm_file in DicomFile.objects.all():
        assert dcm_file.research_project == research_project
        assert dcm_file.file_size_in_mb > 0


def test_files_without_dicom_extension_are_found_too(research_project, tmp_path, settings):
    """PACS exports often lack .dcm — detection is by content, not extension."""
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "pacs_export"
    src.mkdir()
    _write_ct("a", src / "IMG0001", "")
    _write_ct("b", src / "data.bin", "")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 2, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 2


def test_non_dicom_file_in_folder_recorded_as_error_rest_still_processed(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "mixed"
    src.mkdir()
    _write_ct("a", src / "good.dcm", "")
    (src / "notes.txt").write_bytes(b"not a dicom file" * 50)

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    error_result = next(r for r in report.results if r.outcome == "error")
    assert error_result.error == "not a DICOM file"
    assert error_result.source_path.endswith("notes.txt")
    assert DicomFile.objects.count() == 1


def test_empty_folder_completes_with_zero_files_found(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "empty_export"
    src.mkdir()

    report = run_ingestion(research_project, src)

    # Completes — distinct from a run that fails on a missing source
    assert report.results == []
    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 0


def test_single_file_source_still_processed_inside_folder_run_contract(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "one.dcm"
    _write_ct("a", src, "")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert report.results[0].source_path == str(src)


# --- Source validation: missing / inaccessible / allow-list --------------------


def test_missing_local_file_source_fails_run_immediately(research_project, tmp_path):
    with pytest.raises(SourceNotFoundError):
        run_ingestion(research_project, tmp_path / "nope.dcm")
    assert DicomFile.objects.count() == 0


def test_missing_folder_source_fails_run_immediately(research_project, tmp_path):
    with pytest.raises(SourceNotFoundError):
        run_ingestion(research_project, tmp_path / "no_such_export")
    assert DicomFile.objects.count() == 0


def test_inaccessible_folder_source_fails_run_immediately(research_project, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "locked"
    src.mkdir()
    _write_ct("a", src / "a.dcm", "")

    def _blocked_rglob(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    # Simulates the OS refusing to list the directory (EACCES)
    monkeypatch.setattr(Path, "rglob", _blocked_rglob)
    with pytest.raises(SourceInaccessibleError):
        run_ingestion(research_project, src)
    assert DicomFile.objects.count() == 0


def test_source_that_is_neither_file_nor_folder_fails_run_immediately(research_project, tmp_path, settings):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)

    with pytest.raises(SourceInaccessibleError):
        run_ingestion(research_project, fifo)
    assert DicomFile.objects.count() == 0


def test_local_file_source_outside_allow_list_rejected_before_any_read(research_project, tmp_path, settings):
    src = tmp_path / "outside.dcm"
    _write_ct("a", src, "")
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path / "elsewhere"]

    with pytest.raises(SourceNotAllowedError):
        run_ingestion(research_project, src)
    # Nothing was read or ingested
    assert DicomFile.objects.count() == 0


def test_folder_source_outside_allow_list_rejected_before_any_read(research_project, tmp_path, settings):
    src = tmp_path / "export"
    src.mkdir()
    _write_ct("a", src / "a.dcm", "")
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path / "elsewhere"]

    with pytest.raises(SourceNotAllowedError):
        run_ingestion(research_project, src)
    assert DicomFile.objects.count() == 0


def test_no_allow_list_configured_rejects_local_sources(settings, tmp_path, db):
    project = ResearchProject.objects.create(name="Deny all project", description="d")
    settings.DICOM_ALLOWED_SOURCE_ROOTS = []
    src = tmp_path / "a.dcm"
    _write_ct("a", src, "")

    with pytest.raises(SourceNotAllowedError):
        run_ingestion(project, src)
    assert DicomFile.objects.count() == 0


def test_symlink_inside_allowed_dir_escaping_allow_list_is_per_file_error(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    inside = tmp_path / "allowed"
    inside.mkdir()
    (inside / "a.dcm").symlink_to(write_dicom(build_ct_image(), tmp_path / "real_outside.dcm"))
    write_dicom(build_ct_image(sop_instance_uid="1.2.3.4.5.99"), inside / "good.dcm")
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [inside]

    report = run_ingestion(research_project, inside)

    # The escaping link is rejected before read, without aborting the rest of the folder
    assert report.counts["error"] == 1
    assert report.counts["ingested"] == 1
    assert DicomFile.objects.count() == 1


# --- S3 discovery ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def s3_settings(settings):
    """S3 connection settings for the run's discovery client (moto-backed in tests)."""
    settings.DICOM_S3_ENDPOINT_URL = None
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "testing"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "testing"


def _put(client: boto3.client, bucket: str, key: str, ds, tmp_path, name: str) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=write_dicom(ds, tmp_path / name).read_bytes())


@mock_aws
def test_s3_prefix_ingests_every_file_recursively(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="ingest-bucket")
    _put(client, "ingest-bucket", "study1/a.dcm", build_ct_image(patient_id="P-A", study_instance_uid=STUDY_UIDS["a"][0], series_instance_uid=STUDY_UIDS["a"][1], sop_instance_uid=STUDY_UIDS["a"][2]), tmp_path, "a.dcm")
    _put(client, "ingest-bucket", "study1/sub/b.dcm", build_ct_image(patient_id="P-B", study_instance_uid=STUDY_UIDS["b"][0], series_instance_uid=STUDY_UIDS["b"][1], sop_instance_uid=STUDY_UIDS["b"][2]), tmp_path, "b.dcm")
    client.put_object(Bucket="ingest-bucket", Key="study1/notes.txt", Body=b"not a dicom file" * 50)

    report = run_ingestion(research_project, "s3://ingest-bucket/study1")

    assert report.counts == {"ingested": 2, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    assert DicomFile.objects.count() == 2
    # Report addresses S3 objects by their S3 URI, never a local path
    paths = sorted(r.source_path for r in report.results)
    assert paths == ["s3://ingest-bucket/study1/a.dcm", "s3://ingest-bucket/study1/notes.txt", "s3://ingest-bucket/study1/sub/b.dcm"]


@mock_aws
def test_s3_bucket_without_prefix_ingests_whole_bucket(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="whole-bucket")
    _put(client, "whole-bucket", "root.dcm", build_ct_image(patient_id="P-A"), tmp_path, "root.dcm")
    _put(client, "whole-bucket", "deep/nest/x.dcm", build_ct_image(patient_id="P-B", study_instance_uid=STUDY_UIDS["b"][0], series_instance_uid=STUDY_UIDS["b"][1], sop_instance_uid=STUDY_UIDS["b"][2]), tmp_path, "x.dcm")

    report = run_ingestion(research_project, "s3://whole-bucket")

    assert report.counts == {"ingested": 2, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 2


@mock_aws
def test_s3_missing_bucket_fails_run_immediately(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"

    with pytest.raises(S3SourceError):
        run_ingestion(research_project, "s3://no-such-bucket/prefix")
    assert DicomFile.objects.count() == 0


@mock_aws
def test_s3_empty_prefix_completes_with_zero_files(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="empty-bucket")

    report = run_ingestion(research_project, "s3://empty-bucket/prefix")

    assert report.results == []
    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}


@mock_aws
def test_malicious_s3_key_never_builds_local_filesystem_path(research_project, tmp_path, settings):
    """A crafted object key cannot write outside the app's media storage (#114)."""
    media = tmp_path / "media"
    settings.MEDIA_ROOT = media
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="hostile-bucket")
    hostile_key = "../../evil.dcm"
    _put(client, "hostile-bucket", hostile_key, build_ct_image(patient_id="P-A"), tmp_path, "evil.dcm")

    report = run_ingestion(research_project, "s3://hostile-bucket")

    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    stored_path = os.path.realpath(dcm_file.file.path)
    assert stored_path.startswith(os.path.realpath(str(media)) + os.sep)
    # The key, interpreted as a local relative path (from the project dir or tmp),
    # must not exist anywhere — it was never used to build a local path
    assert not Path.cwd().joinpath(hostile_key).resolve().exists()
    assert not (tmp_path / hostile_key).resolve().exists()

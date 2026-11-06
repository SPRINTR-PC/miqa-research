"""DICOM ingestion source retention (#123) — exercises the top-level pipeline
seam `run_ingestion` directly, per the #98 testing decisions.

Retention is layered: `run_ingestion(..., delete_originals_after_storage=...)`
overrides `ResearchProject.dicom_delete_originals_after_storage`, which
overrides `settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE` (most-specific-wins).
Whichever way it's enabled, a source is deleted only once its stored copy is
read back and confirmed to match — never merely because the storage call
returned without error, and never for a duplicate whose bytes weren't written
to storage this run.
"""
import boto3
import pytest
from moto import mock_aws

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling import storage as storage_stage
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
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
    return ResearchProject.objects.create(name="Source retention project", description="Project for #123 tests")


# --- Default behaviour, and the global setting -----------------------------------


def test_retention_disabled_by_default_source_kept(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    assert src.exists()


def test_global_setting_enables_deletion_after_verified_storage(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    assert not src.exists()
    # The stored copy is untouched -- only the source was removed
    dcm_file = DicomFile.objects.get()
    with dcm_file.file.open("rb") as stored:
        assert stored.read()


# --- Precedence: run override > project override > global default ----------------


def test_project_override_enables_deletion_though_global_default_is_off(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = False
    research_project.dicom_delete_originals_after_storage = True
    research_project.save()
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    run_ingestion(research_project, src)

    assert not src.exists()


def test_project_override_disables_deletion_though_global_default_is_on(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    research_project.dicom_delete_originals_after_storage = False
    research_project.save()
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    run_ingestion(research_project, src)

    assert src.exists()


def test_run_override_wins_over_project_and_global(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    research_project.dicom_delete_originals_after_storage = True
    research_project.save()
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    run_ingestion(research_project, src, delete_originals_after_storage=False)

    assert src.exists()


def test_run_override_enables_deletion_though_project_and_global_are_off(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = False
    research_project.dicom_delete_originals_after_storage = False
    research_project.save()
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    run_ingestion(research_project, src, delete_originals_after_storage=True)

    assert not src.exists()


# --- Verification gates deletion --------------------------------------------------


def test_verification_failure_never_deletes_source(monkeypatch, research_project, tmp_path, settings):
    """Simulated storage corruption: the write call succeeds but the persisted
    bytes don't match what was read from the source. The record is still
    created (this ticket doesn't change ingestion outcomes), but the source
    must survive since its storage was never actually confirmed."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    real_store_file_bytes = storage_stage.store_file_bytes

    def corrupting_store(dcm_file, raw_bytes):
        real_store_file_bytes(dcm_file, raw_bytes[:-1] + bytes([raw_bytes[-1] ^ 0xFF]))

    monkeypatch.setattr(storage_stage, "store_file_bytes", corrupting_store)

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    assert src.exists()


def test_duplicate_conflict_left_unwritten_never_deletes_source(research_project, tmp_path, settings):
    """Skip-mode conflict: content differs from what's stored, nothing is
    written this run, so nothing was verified -- the source must survive."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    ds = build_ct_image()
    first = write_dicom(ds, tmp_path / "first.dcm")
    run_ingestion(research_project, first)
    assert not first.exists()  # the first copy's own source is deleted

    ds_rescan = build_ct_image()
    ds_rescan.KVP = "140"  # same SOP Instance UID, different content
    rescan = write_dicom(ds_rescan, tmp_path / "rescan.dcm")

    report = run_ingestion(research_project, rescan, overwrite_existing=False)

    assert report.counts["duplicate_conflict"] == 1
    assert rescan.exists()


def test_skipped_duplicate_never_deletes_source(research_project, tmp_path, settings):
    """Identical-content duplicate: storage already holds a verified match
    from the earlier run, but nothing is verified *this* run -- the second
    source must survive."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    ds = build_ct_image()
    first = write_dicom(ds, tmp_path / "first.dcm")
    run_ingestion(research_project, first)

    rescan = write_dicom(build_ct_image(), tmp_path / "rescan.dcm")

    report = run_ingestion(research_project, rescan)

    assert report.counts["skipped_duplicate"] == 1
    assert rescan.exists()


def test_duplicate_conflict_update_deletes_its_own_source_once_verified(research_project, tmp_path, settings):
    """Update-mode conflict: new bytes are written and verified this run --
    the incoming file's own source is eligible for deletion just like a fresh
    ingest."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    ds = build_ct_image()
    first = write_dicom(ds, tmp_path / "first.dcm")
    run_ingestion(research_project, first)

    ds_rescan = build_ct_image()
    ds_rescan.KVP = "140"
    rescan = write_dicom(ds_rescan, tmp_path / "rescan.dcm")

    report = run_ingestion(research_project, rescan, overwrite_existing=True)

    assert report.counts["duplicate_conflict"] == 1
    assert not rescan.exists()


# --- Exactness: never removes more than the verified file -------------------------


def test_deletion_touches_only_the_exact_verified_file(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    ingestible = write_dicom(build_ct_image(patient_id="P-A"), tmp_path / "folder" / "a.dcm")
    sibling = tmp_path / "folder" / "notes.txt"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_bytes(b"not a dicom file" * 20)

    report = run_ingestion(research_project, tmp_path / "folder")

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    assert not ingestible.exists()
    assert sibling.exists()  # never touched -- it was never ingested/verified


# --- S3 sources ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def s3_settings(settings):
    settings.DICOM_S3_ENDPOINT_URL = None
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "testing"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "testing"


@mock_aws
def test_s3_source_object_deleted_after_verified_storage(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="ingest-bucket")
    client.put_object(
        Bucket="ingest-bucket", Key="a.dcm", Body=write_dicom(build_ct_image(), tmp_path / "a.dcm").read_bytes())
    client.put_object(Bucket="ingest-bucket", Key="notes.txt", Body=b"not a dicom file" * 20)

    report = run_ingestion(research_project, "s3://ingest-bucket")

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    remaining_keys = {obj["Key"] for obj in client.list_objects_v2(Bucket="ingest-bucket").get("Contents", ())}
    # The ingested/verified object is gone; the untouched non-DICOM object survives
    assert remaining_keys == {"notes.txt"}


@mock_aws
def test_s3_source_object_kept_when_retention_disabled(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="ingest-bucket")
    client.put_object(
        Bucket="ingest-bucket", Key="a.dcm", Body=write_dicom(build_ct_image(), tmp_path / "a.dcm").read_bytes())

    run_ingestion(research_project, "s3://ingest-bucket")

    remaining_keys = {obj["Key"] for obj in client.list_objects_v2(Bucket="ingest-bucket").get("Contents", ())}
    assert remaining_keys == {"a.dcm"}

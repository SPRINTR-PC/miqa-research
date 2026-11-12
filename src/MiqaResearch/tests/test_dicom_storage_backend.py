"""S3-compatible object storage backend for DICOM ingestion (#122).

Per the #98 testing decisions: tests exercise the `ingest_files` seam (and,
for the real-multipart case, the `DicomStorage` seam directly) and assert on
what ends up stored/retrievable, never on internal call sequences.

The mocked-S3 tests (moto, in-memory) cover AC #1/#2 (backend toggle,
byte-identical write/read, default-local unaffected -- unaffected-by-default
is also covered directly by test_dicom_ingestion_single_file.py, unchanged by
this ticket) and AC #3 (no migration on switch). The `long_running`-marked
test covers AC #4: a real multipart upload against the dev-test RustFS
container.
"""
import os

import boto3
import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from moto import mock_aws

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.data.models.dicom_storage import DicomStorage
from tests.dicom_fixtures import build_ct_image, write_dicom
from tests.dicom_ingest_helper import ingest_files


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Storage backend project", description="Project for #122 tests")


@pytest.fixture
def s3_backend(settings):
    """Point DicomFile.file's storage at a moto-mocked S3 bucket."""
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-storage"
    settings.DICOM_S3_ENDPOINT_URL = None
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "testing"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "testing"


@mock_aws
def test_s3_backend_writes_to_s3_not_local_disk_and_stays_retrievable(research_project, tmp_path, settings, s3_backend):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="dicom-storage")
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")
    raw_bytes = src.read_bytes()

    report = ingest_files(research_project, src)

    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    # Not on local disk -- MEDIA_ROOT stays untouched by an S3-backed write
    assert not (tmp_path / "media" / "DICOM").exists()
    # Present in the configured bucket, byte-identical to the source
    stored = boto3.client("s3", region_name="us-east-1").get_object(Bucket="dicom-storage", Key=dcm_file.file.name)
    assert stored["Body"].read() == raw_bytes
    # Retrievable back through the model field too (proves round-trip, not just the raw client)
    with dcm_file.file.open("rb") as stored_via_field:
        assert stored_via_field.read() == raw_bytes


def test_default_backend_setting_is_local(settings):
    """AC #2: nothing about DICOM_STORAGE_BACKEND's default changes existing local behavior."""
    assert settings.DICOM_STORAGE_BACKEND == "local"


def test_switching_backend_needs_no_new_migration(settings, db):
    """AC #3: flipping DICOM_STORAGE_BACKEND must never require a schema migration.

    `makemigrations --check` exits non-zero (raising SystemExit via
    call_command) the moment any model field's state disagrees with the
    latest migration -- so this fails loudly if DicomStorage's deconstructed
    form ever starts depending on the backend it currently resolves to.
    """
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "irrelevant-to-this-check"

    call_command("makemigrations", check_changes=True, dry_run=True, verbosity=0)


def test_real_rustfs_endpoint_hostname_is_valid_for_boto3():
    """#171: a recent botocore's `is_valid_endpoint_url` check rejects
    underscore-containing hostnames, so the default
    MIRES_TEST_DICOM_S3_ENDPOINT_URL the long_running test below falls back
    to must resolve to a hostname without one -- construction alone (no
    network I/O) is enough to trigger the check, so this runs fast and in
    the default suite, unlike the long_running test itself which needs a
    live RustFS.
    """
    default_endpoint_url = os.environ.get("MIRES_TEST_DICOM_S3_ENDPOINT_URL", "http://miresfs:9000")

    boto3.client(
        "s3",
        endpoint_url=default_endpoint_url,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.mark.long_running
def test_real_multipart_upload_round_trip_against_rustfs(settings, rustfs_endpoint):
    """AC #4: a real multipart upload against the dev-test RustFS container.

    Targets the `mires_fs` service from docker-compose.dev-test.yml, by its
    `miresfs` hostname/container name (#171: the `mires_fs` service name
    itself contains an underscore, which a recent botocore rejects as an
    invalid endpoint hostname -- same fix as `mires_rabbit`'s `miresrabbit`).
    Runs inside `mires_testrunner` (same `mires` docker network) by default;
    override MIRES_TEST_DICOM_S3_ENDPOINT_URL to point elsewhere (e.g.
    http://localhost:9000 when running outside docker with the service
    port-forwarded).
    """
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-long-running-test"
    settings.DICOM_S3_ENDPOINT_URL = rustfs_endpoint
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "MiresAccessKey"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "MiresSecretKey"

    client = boto3.client(
        "s3",
        endpoint_url=settings.DICOM_S3_ENDPOINT_URL,
        region_name=settings.DICOM_S3_REGION_NAME,
        aws_access_key_id=settings.DICOM_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.DICOM_S3_SECRET_ACCESS_KEY,
    )
    if not any(b["Name"] == settings.DICOM_S3_BUCKET for b in client.list_buckets().get("Buckets", [])):
        client.create_bucket(Bucket=settings.DICOM_S3_BUCKET)

    # Comfortably past boto3's default 8MB multipart threshold, so the
    # upload actually exercises RustFS's multipart path (#122 AC #4;
    # research #108 flagged multipart-specific bugs in RustFS).
    large_bytes = os.urandom(24 * 1024 * 1024)

    storage = DicomStorage()
    name = storage.save("long-running/multipart-roundtrip.bin", ContentFile(large_bytes))
    try:
        with storage.open(name, "rb") as retrieved:
            assert retrieved.read() == large_bytes
    finally:
        storage.delete(name)

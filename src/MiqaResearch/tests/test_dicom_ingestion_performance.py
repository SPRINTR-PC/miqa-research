"""Performance/load test suite for DICOM ingestion (#126).

Three scenarios, each long_running and excluded from the default test run
(pyproject.toml's `-m 'not ... and not long_running ...'`, added by #104):
many small files (throughput), one very large file/series (S3 backend), and
concurrent runs (real task dispatch, #116's one deliberate exception to
"call run_ingestion directly"). All against fully synthetic data.
"""
import itertools
import os

import boto3
import pytest

from MiqaResearch.data.models import ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.mark.long_running
def test_throughput_many_small_files_meets_acceptance_threshold(benchmark, settings, tmp_path, db):
    """AC #1: many small synthetic files, explicit throughput threshold."""
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"
    files_per_round = 200
    acceptance_files_per_second = 15  # see plan doc: measured baseline 40.6/sec, ~2.7x headroom

    project_counter = itertools.count()

    def setup():
        n = next(project_counter)
        project = ResearchProject.objects.create(name=f"Throughput perf project {n}", description="Project for #126 throughput test")
        folder = tmp_path / f"batch-{n}"
        for i in range(files_per_round):
            write_dicom(
                build_ct_image(
                    patient_id=f"P-PERF-{n}-{i}",
                    study_instance_uid=f"1.2.9999.126.1.{n}.{i}.1",
                    series_instance_uid=f"1.2.9999.126.1.{n}.{i}.2",
                    sop_instance_uid=f"1.2.9999.126.1.{n}.{i}.3",
                ),
                folder / f"file-{i}.dcm",
            )
        return (project, folder), {}

    def run(project, folder):
        return run_ingestion(project, folder)

    report = benchmark.pedantic(run, setup=setup, rounds=3, iterations=1)

    assert report.counts["ingested"] == files_per_round
    mean_seconds_per_round = benchmark.stats.stats.mean
    assert mean_seconds_per_round > 0
    files_per_second = files_per_round / mean_seconds_per_round
    assert files_per_second >= acceptance_files_per_second, (
        f"throughput {files_per_second:.1f} files/sec below the {acceptance_files_per_second}/sec threshold"
    )


@pytest.mark.long_running
def test_large_series_via_s3_backend_meets_acceptance_threshold(benchmark, settings, tmp_path, db):
    """AC #2: one very large synthetic file/series, ingested through the real
    S3-compatible backend (RustFS, docker-compose.dev-test.yml's mires_fs --
    same real-backend precedent as test_dicom_storage_backend.py's
    long_running multipart test), explicit acceptance threshold.
    """
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-perf-large-file-test"
    settings.DICOM_S3_ENDPOINT_URL = os.environ.get("MIRES_TEST_DICOM_S3_ENDPOINT_URL", "http://mires_fs:9000")
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

    # 512x512 RGB tiles x 32 frames =~ 25MB of PixelData -- comfortably past
    # boto3's 8MB multipart threshold, same rationale as the AC #4 RustFS test.
    large_file = write_dicom(
        build_wsi(tile_rows=512, tile_columns=512, number_of_frames=32),
        tmp_path / "large-slide.dcm",
    )
    acceptance_seconds = 20  # generous for a ~25MB multipart upload over the docker-compose bridge network

    project_counter = itertools.count()

    def setup():
        n = next(project_counter)
        project = ResearchProject.objects.create(name=f"Large-file perf project {n}", description="Project for #126 large-file test")
        return (project, large_file), {}

    def run(project, source):
        return run_ingestion(project, source)

    report = benchmark.pedantic(run, setup=setup, rounds=2, iterations=1)

    assert report.counts["ingested"] == 1
    assert benchmark.stats.stats.mean < acceptance_seconds, (
        f"large-file ingestion took {benchmark.stats.stats.mean:.1f}s, over the {acceptance_seconds}s threshold"
    )

"""Performance/load test suite for DICOM ingestion (#126), ported to the ETL path (#419).

Three scenarios, each long_running and excluded from the default test run
(pyproject.toml's `-m 'not ... and not long_running ...'`, added by #104):
many small files in one folder Job (throughput), one very large file/series (S3 backend), and
concurrent Jobs loading into one project. Each Job is the real native script plus the `dicom_instance`
loader; the orchestrator, queue and sandbox are covered by the ETL integration tests. All against fully
synthetic data.
"""
import itertools
import time
from concurrent.futures import ThreadPoolExecutor

import boto3
import pytest
from django.db import connection

from MiqaResearch.data.models import DicomFile, ResearchProject
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom
from tests.dicom_ingest_helper import ingest_files


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.mark.long_running
def test_throughput_many_small_files_meets_acceptance_threshold(benchmark, settings, tmp_path, db):
    """AC #1: many small synthetic files in one folder Job, explicit throughput threshold."""
    settings.MEDIA_ROOT = tmp_path / "media"
    files_per_round = 200
    acceptance_files_per_second = 15  # see plan doc: measured baseline 40.6/sec, ~2.7x headroom

    project_counter = itertools.count()

    def setup():
        n = next(project_counter)
        project = ResearchProject.objects.create(
            name=f"Throughput perf project {n}", description="Project for #126 throughput test"
        )
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
        return ingest_files(project, folder)

    report = benchmark.pedantic(run, setup=setup, rounds=3, iterations=1)

    assert report.counts["ingested"] == files_per_round
    mean_seconds_per_round = benchmark.stats.stats.mean
    assert mean_seconds_per_round > 0
    files_per_second = files_per_round / mean_seconds_per_round
    assert files_per_second >= acceptance_files_per_second, (
        f"throughput {files_per_second:.1f} files/sec below the {acceptance_files_per_second}/sec threshold"
    )


@pytest.mark.long_running
def test_large_series_via_s3_backend_meets_acceptance_threshold(
        benchmark, settings, tmp_path, db, rustfs_endpoint):
    """AC #2: one very large synthetic file/series, ingested through the real
    S3-compatible backend (RustFS, docker-compose.dev-test.yml's mires_fs
    service, reached by its `miresfs` hostname -- same real-backend
    precedent as test_dicom_storage_backend.py's long_running multipart
    test), explicit acceptance threshold.
    """
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-perf-large-file-test"
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
        project = ResearchProject.objects.create(
            name=f"Large-file perf project {n}", description="Project for #126 large-file test"
        )
        return (project, large_file), {}

    def run(project, source):
        return ingest_files(project, source)

    report = benchmark.pedantic(run, setup=setup, rounds=2, iterations=1)

    assert report.counts["ingested"] == 1
    assert benchmark.stats.stats.mean < acceptance_seconds, (
        f"large-file ingestion took {benchmark.stats.stats.mean:.1f}s, over the {acceptance_seconds}s threshold"
    )




@pytest.mark.long_running
def test_concurrent_jobs_loading_into_one_project_complete_correctly_and_within_threshold(
    settings, tmp_path, transactional_db
):
    """AC #3: several Jobs loading into the same project at once (one thread, one DB connection each),
    the shape of concurrent `run_etl_job` workers: every Job succeeds, nothing is lost or duplicated, and
    the whole batch finishes within the threshold. The queue and sandbox are covered by the ETL
    integration tests; this exercises the loader's concurrent writes."""
    settings.MEDIA_ROOT = tmp_path / "media"
    project = ResearchProject.objects.create(
        name="Concurrency perf project", description="Project for #126 concurrency test")
    run_count, files_per_run = 4, 10
    acceptance_seconds = 60  # generous: script + load of 10 files per Job, contending on one project

    folders = []
    for run in range(run_count):
        folder = tmp_path / f"run-{run}"
        for i in range(files_per_run):
            write_dicom(
                build_ct_image(
                    patient_id=f"P-CONC-{run}-{i}",
                    study_instance_uid=f"1.2.9999.126.3.{run}.{i}.1",
                    series_instance_uid=f"1.2.9999.126.3.{run}.{i}.2",
                    sop_instance_uid=f"1.2.9999.126.3.{run}.{i}.3",
                ),
                folder / f"file-{i}.dcm",
            )
        folders.append(folder)

    def run_job(folder):
        try:
            return ingest_files(project, folder).counts
        finally:
            connection.close()

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=run_count) as pool:
        counts = list(pool.map(run_job, folders))
    elapsed = time.monotonic() - start

    assert counts == [{"ingested": files_per_run, "skipped": 0}] * run_count
    assert elapsed < acceptance_seconds, (
        f"{run_count} concurrent Jobs took {elapsed:.1f}s, over the {acceptance_seconds}s threshold")
    assert DicomFile.objects.filter(research_project=project).count() == run_count * files_per_run

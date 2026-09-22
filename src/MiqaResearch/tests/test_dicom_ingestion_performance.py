"""Performance/load test suite for DICOM ingestion (#126).

Three scenarios, each long_running and excluded from the default test run
(pyproject.toml's `-m 'not ... and not long_running ...'`, added by #104):
many small files (throughput), one very large file/series (S3 backend), and
concurrent runs (real task dispatch, #116's one deliberate exception to
"call run_ingestion directly"). All against fully synthetic data.
"""
import itertools
import os
import shutil
import time
from pathlib import Path

import boto3
import pytest
from celery.result import AsyncResult
from django.conf import settings as django_settings

from MiqaResearch.celery import app as celery_app
from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from MiqaResearch.tasks.dicom_handling.tasks import ingest_dicom_source
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


@pytest.mark.long_running
def test_concurrent_ingestion_runs_via_real_task_dispatch_complete_correctly_and_within_threshold(settings, transactional_db):
    """AC #3: concurrent ingestion dispatched as real tasks on the actual
    queue (#116's one deliberate exception to calling run_ingestion
    directly) -- not in-process calls.

    Requires a live mires_worker_dicom consuming `dicomIngestion` (see
    docker-compose.dev-test.yml). The scratch source path below must match
    that worker's MIRES_DICOM_ALLOWED_SOURCE_ROOTS env var exactly -- this
    test's own settings overrides only apply in *this* process; the
    dispatched task runs inside the worker container.

    Storage stays local (the default): this codebase's MIRES_MEDIA_ROOT env
    var is declared but never actually wired to Django's MEDIA_ROOT setting
    (a pre-existing, out-of-scope gap -- found live, when local-backend
    output landed at the worker container's CWD instead of the intended
    scratch path), so there is no way to point the worker's storage output
    at a scratch location via env var. Rather than depend on that gap (or on
    S3/RustFS, whose `mires_fs` hostname trips a separate pre-existing,
    out-of-scope botocore endpoint-validation issue in this environment --
    also reproduced against the already-merged AC #4 RustFS test in
    test_dicom_storage_backend.py), this test accepts the CWD-relative
    `DICOM/` folder Django's un-configured default FileSystemStorage
    produces and removes it afterward, same as it does its own scratch root.

    Uses `transactional_db`, not `db`: the default `db` fixture wraps the
    test in one outer transaction rolled back at the end, so a separate
    process (the worker, on its own DB connection) would never see the
    ResearchProject row this test creates. `transactional_db` commits for
    real, which any other process needs in order to see this test's writes.

    Polls via Celery's own `AsyncResult`, not `django.tasks`'s
    `TaskResult.refresh()`/`.return_value` -- found live, against this
    environment's pinned versions, that `django_tasks_celery`'s extended
    django-db-backend metadata bridging chokes on kwargs/args the "django-db"
    Celery result backend stores as JSON *strings* (`meta_to_task_result`
    does `dict(meta["kwargs"])`, expecting an already-decoded dict, and gets
    the literal 2-character string `"{}"` instead -- ValueError). `enqueue()`
    dispatch is unaffected; only that particular result-reading path is.
    """
    # Undo tests/conftest.py's autouse dummy-backend override so this run
    # actually goes through django_tasks_celery.CeleryBackend.
    settings.TASKS = {
        **settings.TASKS,
        "default": {**settings.TASKS["default"], "BACKEND": "django_tasks_celery.CeleryBackend"},
    }
    scratch_root = Path(django_settings.BASE_DIR) / ".dev-data" / "dicom_perf_concurrency"
    # Where the worker's un-configured default FileSystemStorage actually
    # lands (its CWD is /app, same as this process's BASE_DIR -- see
    # docstring above); cleaned up alongside scratch_root.
    stray_media_root = Path(django_settings.BASE_DIR) / "DICOM"
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [scratch_root]
    settings.DICOM_STORAGE_BACKEND = "local"

    shutil.rmtree(scratch_root, ignore_errors=True)
    scratch_root.mkdir(parents=True, exist_ok=True)
    try:
        project = ResearchProject.objects.create(name="Concurrency perf project", description="Project for #126 concurrency test")
        run_count = 4
        files_per_run = 10
        acceptance_seconds = 60  # generous: dispatch + queue + worker pickup + ingest + result round-trip, over docker-compose

        sources = []
        for run in range(run_count):
            folder = scratch_root / f"run-{run}"
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
            sources.append(str(folder))

        start = time.monotonic()
        task_results = [ingest_dicom_source.enqueue(str(project.id), source) for source in sources]
        async_results = [AsyncResult(result.id, app=celery_app) for result in task_results]

        deadline = start + acceptance_seconds
        while not all(ar.ready() for ar in async_results) and time.monotonic() < deadline:
            time.sleep(0.5)
        elapsed = time.monotonic() - start

        assert all(ar.ready() for ar in async_results), "not every dispatched run finished before the deadline"
        assert all(ar.successful() for ar in async_results), [
            (ar.id, ar.state, ar.result) for ar in async_results if not ar.successful()
        ]
        assert elapsed < acceptance_seconds, f"{run_count} concurrent runs took {elapsed:.1f}s, over the {acceptance_seconds}s threshold"

        for ar in async_results:
            payload = ar.get()
            assert payload["counts"] == {
                "ingested": files_per_run, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0,
            }
            assert len(payload["results"]) == files_per_run
            assert all(result["outcome"] == "ingested" for result in payload["results"])
        assert DicomFile.objects.filter(research_project=project).count() == run_count * files_per_run
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
        shutil.rmtree(stray_media_root, ignore_errors=True)

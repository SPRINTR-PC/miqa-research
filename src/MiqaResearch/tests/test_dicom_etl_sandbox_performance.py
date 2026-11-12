"""Performance, concurrency and memory-ceiling tests for DICOM ingestion on the real ETL path (#423, spec #411).

Ports of #126's three scenarios (the in-process versions in test_dicom_ingestion_performance.py, #419, keep
the script + loader on the host): here each Job runs the native `dicom_instance` script inside the real
`mires-etl-sandbox-python:dev` container (Compose backend) and then the loader. All `long_running`, all
synthetic data. The orchestrator/queue are covered by the ETL integration tests, so each Job is
`tests.sandbox_dicom.run_dicom_job`: real container run + real loader over the staged originals.
"""
import itertools
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor

import boto3
import pytest
from django.db import connection

from MiqaResearch.data.models import DicomFile, ResearchProject
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom
from tests.sandbox_dicom import compose_backend, run_dicom_job, sandbox_limits

MIB = 1024 ** 2


@pytest.fixture(autouse=True)
def _keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.mark.long_running
def test_many_small_files_in_one_folder_job_meet_the_throughput_threshold(settings, tmp_path, db):
    """Throughput: 200 small files in one folder Job, real container + loader, files/sec over the whole Job."""
    settings.MEDIA_ROOT = tmp_path / "media"
    backend = compose_backend(settings)
    file_count = 200
    acceptance_files_per_second = 10  # container start + staging overhead on top of the in-process 15/sec bar
    project = ResearchProject.objects.create(name="ETL throughput perf project", description="")
    folder = tmp_path / "batch"
    for i in range(file_count):
        write_dicom(
            build_ct_image(
                patient_id=f"P-PERF-{i}", study_instance_uid=f"1.2.9999.423.1.{i}.1",
                series_instance_uid=f"1.2.9999.423.1.{i}.2", sop_instance_uid=f"1.2.9999.423.1.{i}.3"),
            folder / f"file-{i}.dcm")

    start = time.monotonic()
    _, load_result = run_dicom_job(backend, project, folder, run_id="perf-throughput")
    elapsed = time.monotonic() - start

    assert load_result.created == file_count
    assert file_count / elapsed >= acceptance_files_per_second, (
        f"throughput {file_count / elapsed:.1f} files/sec below the {acceptance_files_per_second}/sec threshold")


@pytest.mark.long_running
def test_large_series_via_s3_backend_meets_the_threshold(settings, tmp_path, db, rustfs_endpoint):
    """One large series (a ~25 MB WSI plus a CT stack) through the real container, stored on the real S3 backend
    (RustFS, `mires_fs`, same precedent as test_dicom_storage_backend.py's multipart test)."""
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-etl-perf-large-test"
    settings.DICOM_S3_ENDPOINT_URL = rustfs_endpoint
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "MiresAccessKey"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "MiresSecretKey"
    s3 = boto3.client(
        "s3", endpoint_url=rustfs_endpoint, region_name="us-east-1",
        aws_access_key_id="MiresAccessKey", aws_secret_access_key="MiresSecretKey")
    if not any(b["Name"] == settings.DICOM_S3_BUCKET for b in s3.list_buckets().get("Buckets", [])):
        s3.create_bucket(Bucket=settings.DICOM_S3_BUCKET)
    backend = compose_backend(settings)
    # 512x512 RGB tiles x 32 frames =~ 25 MB of PixelData: past boto3's 8 MB multipart threshold.
    folder = tmp_path / "series"
    write_dicom(build_wsi(tile_rows=512, tile_columns=512, number_of_frames=32), folder / "large-slide.dcm")
    for i in range(10):
        write_dicom(
            build_ct_image(
                study_instance_uid="1.2.9999.423.2.1", series_instance_uid="1.2.9999.423.2.2",
                sop_instance_uid=f"1.2.9999.423.2.3.{i}"),
            folder / f"ct-{i}.dcm")
    acceptance_seconds = 60
    project = ResearchProject.objects.create(name="ETL large series perf project", description="")

    start = time.monotonic()
    _, load_result = run_dicom_job(backend, project, folder, run_id="perf-large-s3")
    elapsed = time.monotonic() - start

    assert load_result.created == 11
    assert elapsed < acceptance_seconds, f"large series took {elapsed:.1f}s, over the {acceptance_seconds}s threshold"
    assert s3.list_objects_v2(Bucket=settings.DICOM_S3_BUCKET).get("KeyCount", 0) >= 11


@pytest.mark.long_running
def test_concurrent_real_sandbox_jobs_into_one_project_complete_correctly(settings, tmp_path, transactional_db):
    """Several Jobs at once, each its own real container and DB connection (the shape of concurrent
    `run_etl_job` workers): every Job succeeds, nothing is lost or duplicated, within the threshold."""
    settings.MEDIA_ROOT = tmp_path / "media"
    compose_backend(settings)  # ensures the image and points settings at the daemon
    project = ResearchProject.objects.create(name="ETL concurrency perf project", description="")
    run_count, files_per_run, acceptance_seconds = 4, 10, 120
    folders = []
    for run in range(run_count):
        folder = tmp_path / f"run-{run}"
        for i in range(files_per_run):
            write_dicom(
                build_ct_image(
                    patient_id=f"P-CONC-{run}-{i}", study_instance_uid=f"1.2.9999.423.3.{run}.{i}.1",
                    series_instance_uid=f"1.2.9999.423.3.{run}.{i}.2", sop_instance_uid=f"1.2.9999.423.3.{run}.{i}.3"),
                folder / f"file-{i}.dcm")
        folders.append(folder)
    counter = itertools.count()

    def job(folder):
        try:
            run_id = f"perf-concurrent-{next(counter)}"
            _, load_result = run_dicom_job(compose_backend(settings), project, folder, run_id=run_id)
            return load_result.created
        finally:
            connection.close()

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=run_count) as pool:
        created = list(pool.map(job, folders))
    elapsed = time.monotonic() - start

    assert created == [files_per_run] * run_count
    assert elapsed < acceptance_seconds, f"{run_count} concurrent Jobs took {elapsed:.1f}s, over {acceptance_seconds}s"
    assert DicomFile.objects.filter(research_project=project).count() == run_count * files_per_run


@pytest.mark.long_running
def test_a_multi_gigabyte_folder_job_stays_under_the_memory_ceiling(settings, tmp_path, db):
    """Memory ceiling (#406 spirit): 40 files x 64 MiB = 2.5 GiB folder through a sandbox capped at 256 MiB.

    Two ceilings: the container (cgroup limit; an OOM would surface as exit code 3, failing the Job) and the
    host-side loader, whose Python-allocation peak (tracemalloc, covering every bytes buffer it reads) must stay
    under 256 MiB (measured ~130 MiB), i.e. at most ~1/10 of the input: it must hold roughly one file at a time, never the folder."""
    settings.MEDIA_ROOT = tmp_path / "media"
    backend = compose_backend(settings)
    file_count, pixel_edge = 40, 8192  # 8192 x 8192 x 8 bit = 64 MiB of PixelData per file
    pixels = bytes(pixel_edge * pixel_edge)
    folder = tmp_path / "big"
    for i in range(file_count):
        ds = build_ct_image(
            patient_id=f"P-MEM-{i % 4}", study_instance_uid=f"1.2.9999.423.4.{i}.1",
            series_instance_uid=f"1.2.9999.423.4.{i}.2", sop_instance_uid=f"1.2.9999.423.4.{i}.3")
        ds.Rows = ds.Columns = pixel_edge
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
        ds.PixelData = pixels
        write_dicom(ds, folder / f"big-{i}.dcm")
    total_bytes = sum(p.stat().st_size for p in folder.iterdir())
    assert total_bytes > 2.5 * 1024 ** 3
    project = ResearchProject.objects.create(name="ETL memory ceiling project", description="")

    tracemalloc.start()
    try:
        _, load_result = run_dicom_job(
            backend, project, folder, run_id="perf-memory-ceiling",
            limits=sandbox_limits(memory_mb=256, timeout_seconds=1200))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    print(f"memory ceiling: loader peak {peak / MIB:.0f} MiB for {total_bytes / MIB:.0f} MiB of input")
    assert load_result.created == file_count
    assert peak < 256 * MIB, f"loader peaked at {peak / MIB:.0f} MiB loading {total_bytes / MIB:.0f} MiB"

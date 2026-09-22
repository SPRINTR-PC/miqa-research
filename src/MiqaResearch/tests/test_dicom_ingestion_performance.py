"""Performance/load test suite for DICOM ingestion (#126).

Three scenarios, each long_running and excluded from the default test run
(pyproject.toml's `-m 'not ... and not long_running ...'`, added by #104):
many small files (throughput), one very large file/series (S3 backend), and
concurrent runs (real task dispatch, #116's one deliberate exception to
"call run_ingestion directly"). All against fully synthetic data.
"""
import itertools

import pytest

from MiqaResearch.data.models import ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, write_dicom


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

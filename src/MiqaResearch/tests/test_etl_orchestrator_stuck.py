"""ETL orchestrator (#162): stuck-Job recovery (AC #5). No heartbeat mechanism -- a Job stuck in
"running" past its own resolved sandbox timeout plus a grace period is assumed to have lost its
worker (crashed, OOM-killed, node evicted, ...) and is recovered via the same infra-class retry
path a SandboxBackend.run() connectivity failure takes (retry.py), without manual intervention.
"""
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from contract.constants.etl import (
    ETL_JOB_STATUS_FAILED,
    ETL_JOB_STATUS_PENDING,
    ETL_JOB_STATUS_RUNNING,
    ETL_SCRIPT_ORIGIN_CUSTOM,
)
from MiqaResearch.data.models import EtlJob, EtlScript, EtlScriptVersion, PipelineBinding, ResearchProject
from MiqaResearch.tasks.etl_orchestrator import stuck


class _FakeRunEtlJobTask:
    """Task objects are frozen dataclasses -- swap the whole object rather than its .enqueue."""

    def __init__(self):
        self.enqueued_job_ids = []

    def enqueue(self, job_id):
        self.enqueued_job_ids.append(job_id)


@pytest.fixture(autouse=True)
def fake_run_etl_job_task(monkeypatch):
    fake = _FakeRunEtlJobTask()
    monkeypatch.setattr("MiqaResearch.tasks.etl_orchestrator.tasks.run_etl_job", fake)
    return fake


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def sandbox_defaults(settings):
    settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS = 600
    settings.SANDBOX_DEFAULT_MEMORY_MB = 1024
    settings.SANDBOX_DEFAULT_CPU_MILLICORES = 1000
    settings.SANDBOX_DEFAULT_PIDS_LIMIT = 128
    settings.SANDBOX_MAX_INPUT_BYTES = 15 * 1024 ** 3
    settings.SANDBOX_MAX_OUTPUT_BYTES = 1 * 1024 ** 3
    settings.ETL_JOB_STUCK_GRACE_SECONDS = 300
    settings.ETL_JOB_MAX_AUTO_RETRIES = 3


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Stuck job test project", description="")


@pytest.fixture
def script_version(research_project):
    script = EtlScript.objects.create(name="Importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"x"), sha256="0" * 64)


@pytest.fixture
def binding(research_project, script_version):
    return PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="redcap/",
        script_version=script_version, raw_bucket="raw", raw_prefix="redcap/")


def _running_job(binding, script_version, *, started_at):
    return EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_RUNNING, started_at=started_at)


def test_find_stuck_jobs_ignores_a_job_within_its_timeout_plus_grace(binding, script_version):
    _running_job(binding, script_version, started_at=timezone.now() - timedelta(seconds=60))

    assert stuck.find_stuck_jobs() == []


def test_find_stuck_jobs_finds_a_job_past_its_timeout_plus_grace(binding, script_version):
    # 600s default timeout + 300s grace = 900s; put it well past that.
    job = _running_job(binding, script_version, started_at=timezone.now() - timedelta(seconds=1000))

    assert list(stuck.find_stuck_jobs()) == [job]


def test_find_stuck_jobs_ignores_jobs_not_currently_running(binding, script_version):
    EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_PENDING,
        started_at=timezone.now() - timedelta(seconds=1000))

    assert stuck.find_stuck_jobs() == []


def test_recover_stuck_jobs_fails_the_original_and_queues_a_capped_retry(binding, script_version):
    job = _running_job(binding, script_version, started_at=timezone.now() - timedelta(seconds=1000))

    recovered = stuck.recover_stuck_jobs()

    assert recovered == [job]
    job.refresh_from_db()
    assert job.status == ETL_JOB_STATUS_FAILED
    retry_job = EtlJob.objects.get(retry_of=job)
    assert retry_job.status == ETL_JOB_STATUS_PENDING
    assert retry_job.attempt == 2


def test_recover_stuck_jobs_does_not_retry_once_the_cap_is_reached(binding, script_version, settings):
    settings.ETL_JOB_MAX_AUTO_RETRIES = 1
    job = _running_job(binding, script_version, started_at=timezone.now() - timedelta(seconds=1000))
    job.attempt = 1
    job.save()

    stuck.recover_stuck_jobs()

    job.refresh_from_db()
    assert job.status == ETL_JOB_STATUS_FAILED
    assert not EtlJob.objects.filter(retry_of=job).exists()

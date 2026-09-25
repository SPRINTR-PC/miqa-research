"""ETL orchestrator (#162): the daily log-retention prune task (AC #6). EtlJob.log is already
capped at 64 KB per run by the runner; this additionally clears it once a Job is older than the
effective retention window (a project's EtlProjectSettings.log_retention_days override, else the
global MIRES_ETL_LOG_RETENTION_DAYS default) -- old logs are pruned, newer ones left intact.
"""
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    EtlJob,
    EtlProjectSettings,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
)
from MiqaResearch.tasks.etl_orchestrator import log_retention


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def retention_default(settings):
    settings.ETL_LOG_RETENTION_DAYS = 30


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Log retention test project", description="")


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


def _finished_job(binding, script_version, *, finished_at, log="some log output"):
    job = EtlJob.objects.create(binding=binding, script_version=script_version, log=log)
    EtlJob.objects.filter(pk=job.pk).update(finished_at=finished_at)
    job.refresh_from_db()
    return job


def test_prune_logs_clears_a_log_past_the_global_retention_window(binding, script_version):
    old_job = _finished_job(binding, script_version, finished_at=timezone.now() - timedelta(days=31))

    pruned = log_retention.prune_logs()

    assert pruned == 1
    old_job.refresh_from_db()
    assert old_job.log == ""


def test_prune_logs_leaves_a_log_within_the_retention_window_intact(binding, script_version):
    recent_job = _finished_job(binding, script_version, finished_at=timezone.now() - timedelta(days=1))

    pruned = log_retention.prune_logs()

    assert pruned == 0
    recent_job.refresh_from_db()
    assert recent_job.log == "some log output"


def test_prune_logs_uses_the_project_override_over_the_global_default(research_project, binding, script_version):
    EtlProjectSettings.objects.create(project=research_project, log_retention_days=7)
    job = _finished_job(binding, script_version, finished_at=timezone.now() - timedelta(days=10))

    pruned = log_retention.prune_logs()

    assert pruned == 1
    job.refresh_from_db()
    assert job.log == ""


def test_prune_logs_skips_jobs_with_no_log_to_clear(binding, script_version):
    _finished_job(binding, script_version, finished_at=timezone.now() - timedelta(days=100), log="")

    assert log_retention.prune_logs() == 0

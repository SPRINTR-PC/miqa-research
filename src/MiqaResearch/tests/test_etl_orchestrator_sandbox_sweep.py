"""ETL orchestrator (#225): the periodic orphaned-sandbox sweep. A crashed `QUEUE_ETL_RUN` worker
leaves its sandbox (container, or K8s Job/pods/PVC) behind; stuck-job recovery fails the EtlJob,
but only this sweep removes the sandbox itself. Runs through the Celery task entry point with a
fake SandboxBackend -- the backends' own label filtering is unit-tested in test_etl_sandbox*.py.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import (
    ETL_JOB_STATUS_FAILED,
    ETL_JOB_STATUS_PENDING,
    ETL_JOB_STATUS_RUNNING,
    ETL_JOB_STATUS_SUCCEEDED,
    ETL_SCRIPT_ORIGIN_CUSTOM,
)
from MiqaResearch.data.models import EtlJob, EtlScript, EtlScriptVersion, PipelineBinding, ResearchProject
from MiqaResearch.tasks.etl_orchestrator import sandbox_sweep, tasks


class _RecordingSweepBackend:
    def __init__(self):
        self.live_run_ids = None

    def sweep(self, *, live_run_ids):
        self.live_run_ids = live_run_ids()


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def backend(monkeypatch):
    fake = _RecordingSweepBackend()
    monkeypatch.setattr(sandbox_sweep, "get_sandbox_backend", lambda: fake)
    return fake


@pytest.fixture
def script_version(db):
    project = ResearchProject.objects.create(name="Sandbox sweep project", description="")
    script = EtlScript.objects.create(
        name="Importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="measurement")
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"# unused"), sha256="0" * 64,
        image_key="python-etl-v1")


def _job(script_version, status):
    # One Binding per Job: at most one pending/running Job is allowed per Binding.
    binding = PipelineBinding.objects.create(
        project=script_version.script.project, source_bucket="incoming", source_prefix=f"{status}/",
        script_version=script_version, raw_bucket="raw")
    return EtlJob.objects.create(binding=binding, script_version=script_version, status=status)


@pytest.mark.django_db
def test_only_pending_and_running_jobs_keep_their_sandboxes(backend, script_version):
    pending = _job(script_version, ETL_JOB_STATUS_PENDING)
    running = _job(script_version, ETL_JOB_STATUS_RUNNING)
    _job(script_version, ETL_JOB_STATUS_SUCCEEDED)
    _job(script_version, ETL_JOB_STATUS_FAILED)

    tasks.sweep_orphaned_sandboxes.func()

    assert backend.live_run_ids == {str(pending.id), str(running.id)}

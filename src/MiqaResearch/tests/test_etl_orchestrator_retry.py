"""ETL orchestrator (#162): failure classification + capped auto-retry (AC #4, infra-class half --
the script-class half, exit codes 1/2/3 never auto-retrying, is covered in
test_etl_orchestrator_runner.py since it's a runner concern). SandboxBackend.run() raising means
no container was ever started; that's either a config-class error (UnknownSandboxImage,
SandboxInputTooLarge -- a Binding/Script misconfiguration no retry can fix) or, for anything else
(e.g. the backend being unreachable), infra-class and auto-retried up to the configured cap.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_JOB_STATUS_FAILED, ETL_JOB_STATUS_PENDING, ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import EtlJob, EtlJobInput, EtlScript, EtlScriptVersion, PipelineBinding, ResearchProject
from MiqaResearch.etl_sandbox import SandboxInputTooLarge, UnknownSandboxImage
from MiqaResearch.tasks.etl_orchestrator import runner


class _FakeRunEtlJobTask:
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
def etl_s3_settings(settings):
    settings.ETL_S3_ENDPOINT_URL = None
    settings.ETL_S3_REGION_NAME = "us-east-1"
    settings.ETL_S3_ACCESS_KEY_ID = "testing"
    settings.ETL_S3_SECRET_ACCESS_KEY = "testing"
    settings.ETL_JOB_MAX_AUTO_RETRIES = 3


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Retry test project", description="")


@pytest.fixture
def script_version(research_project):
    script = EtlScript.objects.create(name="Importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"x"), sha256="0" * 64,
        image_key="python-etl-v1")


@pytest.fixture
def binding(research_project, script_version):
    return PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="redcap/",
        script_version=script_version, raw_bucket="raw", raw_prefix="redcap/")


@pytest.fixture
def job(binding, script_version):
    return EtlJob.objects.create(binding=binding, script_version=script_version)


@pytest.fixture
def job_input(job):
    return EtlJobInput.objects.create(job=job, bucket="incoming", key="redcap/export.csv", sha256="", size_bytes=0)


@pytest.fixture
def s3_input(job_input):
    import boto3
    from moto import mock_aws

    ctx = mock_aws()
    ctx.start()
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=job_input.bucket)
    client.put_object(Bucket=job_input.bucket, Key=job_input.key, Body=b"data")
    yield
    ctx.stop()


class _RaisingBackend:
    def __init__(self, exception):
        self.exception = exception

    def run(self, spec):
        raise self.exception


@pytest.mark.parametrize("exc", [UnknownSandboxImage("bad key"), SandboxInputTooLarge("too big")])
def test_config_class_exceptions_fail_permanently_without_a_retry(monkeypatch, job, job_input, s3_input, exc):
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: _RaisingBackend(exc))

    finished = runner.run_job(str(job.id))

    assert finished.status == ETL_JOB_STATUS_FAILED
    assert not EtlJob.objects.filter(retry_of=job).exists()


def test_an_infra_class_exception_queues_a_capped_auto_retry(
        monkeypatch, job, job_input, s3_input, fake_run_etl_job_task):
    monkeypatch.setattr(
        runner, "get_sandbox_backend", lambda: _RaisingBackend(ConnectionError("no route to backend")))

    finished = runner.run_job(str(job.id))

    assert finished.status == ETL_JOB_STATUS_FAILED
    assert "sandbox backend unreachable" in finished.log
    retry_job = EtlJob.objects.get(retry_of=job)
    assert retry_job.status == ETL_JOB_STATUS_PENDING
    assert retry_job.attempt == 2
    assert fake_run_etl_job_task.enqueued_job_ids == [str(retry_job.id)]
    # The retry carries its own copy of the original's inputs, ready to be fetched again.
    assert list(EtlJobInput.objects.filter(job=retry_job).values_list("key", flat=True)) == ["redcap/export.csv"]


def test_auto_retry_copies_the_original_inputs_and_config_snapshot(monkeypatch, binding, job, job_input, s3_input):
    binding.config = {"delimiter": ";"}
    binding.save()
    job.config_snapshot = {"delimiter": ";"}
    job.save()
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: _RaisingBackend(ConnectionError("down")))

    runner.run_job(str(job.id))

    retry_job = EtlJob.objects.get(retry_of=job)
    assert retry_job.config_snapshot == {"delimiter": ";"}


def test_retry_stops_once_the_cap_is_reached(monkeypatch, binding, script_version, settings):
    settings.ETL_JOB_MAX_AUTO_RETRIES = 1
    job = EtlJob.objects.create(binding=binding, script_version=script_version, attempt=1)
    EtlJobInput.objects.create(job=job, bucket="incoming", key="redcap/export.csv", sha256="", size_bytes=0)
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: _RaisingBackend(ConnectionError("down")))
    import boto3
    from moto import mock_aws

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="incoming")
        client.put_object(Bucket="incoming", Key="redcap/export.csv", Body=b"data")

        finished = runner.run_job(str(job.id))

    assert finished.status == ETL_JOB_STATUS_FAILED
    assert not EtlJob.objects.filter(retry_of=job).exists()

"""ETL orchestrator (#162): the Celery task entry points (AC #7 -- tested by direct invocation,
never live Celery beat/dispatch, matching the DICOM ingestion task precedent's `.func(...)`
pattern). The last test exercises the true end-to-end path through the actual task functions:
drop a file, poll queues a Job and dispatches its run, the run succeeds and loads a row --
without a human triggering anything, per #162's own stated goal.
"""
import hashlib
import json
from datetime import date, timedelta

import boto3
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from moto import mock_aws

from contract.constants.etl import (
    ETL_JOB_INPUT_SOURCE_STATUS_MOVED,
    ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING,
    ETL_JOB_STATUS_FAILED,
    ETL_JOB_STATUS_RUNNING,
    ETL_JOB_STATUS_SUCCEEDED,
    ETL_SCRIPT_ORIGIN_CUSTOM,
)
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlLocationGrant,
    EtlScript,
    EtlScriptVersion,
    Measurement,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_sandbox import SandboxRunResult
from MiqaResearch.tasks.etl_orchestrator import runner, tasks
from mires_etl import contract


class _FakeTask:
    """Task objects are frozen dataclasses -- swap the whole module-level name rather than
    setting .enqueue on the instance."""

    def __init__(self, on_enqueue=None):
        self.enqueued = []
        self._on_enqueue = on_enqueue

    def enqueue(self, arg):
        self.enqueued.append(arg)
        if self._on_enqueue is not None:
            self._on_enqueue(arg)


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


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
    settings.ETL_JOB_STUCK_GRACE_SECONDS = 300


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Task wrapper test project", description="")


@pytest.fixture
def script_version(research_project):
    script = EtlScript.objects.create(
        name="Weight importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project,
        datatype_name="measurement")
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"x"), sha256="0" * 64,
        image_key="python-etl-v1")


@pytest.fixture
def binding(research_project, script_version):
    return PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="redcap/",
        script_version=script_version, raw_bucket="raw", raw_prefix="redcap/")


# --- fan_out_etl_polls -------------------------------------------------

def test_fan_out_etl_polls_enqueues_a_poll_for_every_binding(monkeypatch, binding):
    fake = _FakeTask()
    monkeypatch.setattr(tasks, "poll_pipeline_binding", fake)

    result = tasks.fan_out_etl_polls.func()

    assert fake.enqueued == [str(binding.id)]
    assert result == {"bindings_polled": 1}


# --- poll_pipeline_binding -----------------------------------------------

@mock_aws
def test_poll_pipeline_binding_queues_a_job_and_dispatches_its_run(monkeypatch, binding):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"a")
    fake = _FakeTask()
    monkeypatch.setattr(tasks, "run_etl_job", fake)

    result = tasks.poll_pipeline_binding.func(str(binding.id))

    job = EtlJob.objects.get(binding=binding)
    assert result == {"job_id": str(job.id)}
    assert fake.enqueued == [str(job.id)]


@mock_aws
def test_poll_pipeline_binding_returns_none_job_id_when_nothing_is_queued(binding):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="incoming")

    result = tasks.poll_pipeline_binding.func(str(binding.id))

    assert result == {"job_id": None}


# --- run_etl_job -----------------------------------------------------------

@mock_aws
def test_run_etl_job_delegates_to_the_runner_and_reports_status(monkeypatch, binding, script_version):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"a")
    job = EtlJob.objects.create(binding=binding, script_version=script_version)
    from MiqaResearch.data.models import EtlJobInput
    EtlJobInput.objects.create(job=job, bucket="incoming", key="redcap/a.csv", sha256="", size_bytes=0)
    monkeypatch.setattr(
        runner, "get_sandbox_backend",
        lambda: type("B", (), {"run": lambda self, spec: SandboxRunResult(
            exit_code=contract.EXIT_SCRIPT_ERROR, result_jsonl=None, log=b"boom", killed=False)})())

    result = tasks.run_etl_job.func(str(job.id))

    assert result == {"job_id": str(job.id), "status": ETL_JOB_STATUS_FAILED}


# --- recover_stuck_etl_jobs / prune_etl_job_logs --------------------------

def test_recover_stuck_etl_jobs_reports_the_recovered_count(monkeypatch, binding, script_version):
    monkeypatch.setattr(tasks, "run_etl_job", _FakeTask())
    EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_RUNNING,
        started_at=timezone.now() - timedelta(seconds=10_000))

    result = tasks.recover_stuck_etl_jobs.func()

    assert result == {"recovered": 1}


def test_prune_etl_job_logs_reports_the_pruned_count(binding, script_version, settings):
    settings.ETL_LOG_RETENTION_DAYS = 30
    job = EtlJob.objects.create(binding=binding, script_version=script_version, log="old log")
    EtlJob.objects.filter(pk=job.pk).update(finished_at=timezone.now() - timedelta(days=60))

    result = tasks.prune_etl_job_logs.func()

    assert result == {"pruned": 1}


# --- move_etl_job_inputs_to_raw_bucket / retry_etl_source_cleanup (#163) --

@mock_aws
def test_move_etl_job_inputs_to_raw_bucket_delegates_to_the_mover(binding, script_version):
    from MiqaResearch.data.models import EtlJobInput

    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.create_bucket(Bucket="raw")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    EtlLocationGrant.objects.create(project=binding.project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=binding.project, bucket="raw", prefix="")
    job = EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED)
    job_input = EtlJobInput.objects.create(
        job=job, bucket="incoming", key="redcap/a.csv",
        sha256=hashlib.sha256(b"data").hexdigest(), size_bytes=4)

    result = tasks.move_etl_job_inputs_to_raw_bucket.func(str(job.id))

    assert result == {"job_id": str(job.id)}
    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_MOVED


def test_retry_etl_source_cleanup_reports_the_swept_job_count(binding, script_version, settings):
    from MiqaResearch.data.models import EtlJobInput

    job = EtlJob.objects.create(binding=binding, script_version=script_version)
    EtlJobInput.objects.create(
        job=job, bucket="incoming", key="redcap/a.csv", sha256="0" * 64, size_bytes=4,
        source_status=ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING, cleanup_attempts=1,
        cleanup_next_attempt_at=timezone.now() - timedelta(seconds=1))
    EtlLocationGrant.objects.create(project=binding.project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=binding.project, bucket="raw", prefix="")

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="incoming")
        result = tasks.retry_etl_source_cleanup.func()

    assert result == {"jobs_swept": 1}


# --- True end-to-end: poll -> queue -> run -> succeed -> loaded row -------

@pytest.fixture
def study_participant(research_project):
    return StudyParticipant.objects.create(alias1="TASK-P001", research_project=research_project)


@pytest.fixture
def measurement_concept(db):
    return Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))


@mock_aws
def test_dropping_a_file_becomes_a_loaded_row_without_a_human_triggering_anything(
        monkeypatch, binding, study_participant, measurement_concept):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"raw source bytes")

    header = json.dumps({"datatype": "measurement"})
    row = json.dumps({
        "alias1": study_participant.alias1,
        "measurement_concept_id": str(measurement_concept.concept_id),
        "measurement_type_concept_id": str(measurement_concept.concept_id),
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
    })
    fake_result = SandboxRunResult(
        exit_code=contract.EXIT_SUCCESS, result_jsonl=f"{header}\n{row}\n".encode(), log=b"ok", killed=False)
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: type("B", (), {"run": lambda self, spec: fake_result})())
    # poll -> run dispatch happens for real: the fake "enqueue" immediately invokes the real run
    # task's own .func(), simulating what a worker picking up the dispatched task would do.
    real_run_etl_job = tasks.run_etl_job
    monkeypatch.setattr(tasks, "run_etl_job", _FakeTask(on_enqueue=lambda job_id: real_run_etl_job.func(job_id)))

    result = tasks.poll_pipeline_binding.func(str(binding.id))

    job = EtlJob.objects.get(pk=result["job_id"])
    assert job.status == ETL_JOB_STATUS_SUCCEEDED
    measurement = Measurement.objects.get()
    assert measurement.person_id == study_participant.id
    assert measurement.etl_job_id == job.id

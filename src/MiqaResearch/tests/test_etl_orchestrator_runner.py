"""ETL orchestrator (#162): running a queued EtlJob. Exercises the whole path end-to-end against
a fake SandboxBackend (no real container runtime) -- build the manifest/spec from the Binding +
Script Version, run it, and on exit 0 hand the result to the real Datatype loader (#159), so a
successful run genuinely produces loaded DB rows (measurement), matching #162's own stated goal.

Exit codes 1/2/3 are all script-class per #156's spec text ("script error, contract violation,
timeout" all require manual retry) -- covered here as "no auto-retry"; the infra-class,
auto-retried case (SandboxBackend.run() itself raising) is covered in
test_etl_orchestrator_retry.py, since it's shared with stuck-job recovery.
"""
import json
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_JOB_STATUS_FAILED, ETL_JOB_STATUS_SUCCEEDED, ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlJobInput,
    EtlScript,
    EtlScriptVersion,
    Measurement,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_shim import contract
from MiqaResearch.tasks.etl_orchestrator import runner


class FakeSandboxBackend:
    def __init__(self, result=None, exception=None):
        self.result = result
        self.exception = exception
        self.received_spec = None

    def run(self, spec):
        self.received_spec = spec
        if self.exception is not None:
            raise self.exception
        return self.result

    def cancel(self, run_id):
        raise AssertionError("not exercised by the runner")

    def sweep(self):
        raise AssertionError("not exercised by the runner")


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


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Runner test project", description="")


@pytest.fixture
def study_participant(research_project):
    return StudyParticipant.objects.create(alias1="RUN-P001", research_project=research_project)


@pytest.fixture
def measurement_concept(db):
    return Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))


@pytest.fixture
def script_version(research_project):
    script = EtlScript.objects.create(
        name="Weight importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project,
        datatype_name="measurement")
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"# real source unused by the fake backend"),
        sha256="0" * 64, image_key="python-etl-v1")


@pytest.fixture
def binding(research_project, script_version):
    return PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="redcap/",
        script_version=script_version, raw_bucket="raw", raw_prefix="redcap/",
        config={"delimiter": ","})


@pytest.fixture
def job(binding, script_version):
    return EtlJob.objects.create(binding=binding, script_version=script_version, config_snapshot=binding.config)


@pytest.fixture
def job_input(job):
    return EtlJobInput.objects.create(job=job, bucket="incoming", key="redcap/export.csv", sha256="", size_bytes=0)


def _measurement_row_jsonl(participant, concept):
    header = json.dumps({"datatype": "measurement"})
    row = json.dumps({
        "alias1": participant.alias1,
        "measurement_concept_id": str(concept.concept_id),
        "measurement_type_concept_id": str(concept.concept_id),
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
    })
    return f"{header}\n{row}\n".encode()


def _put_source_object(job_input):
    import boto3
    from moto import mock_aws

    ctx = mock_aws()
    ctx.start()
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=job_input.bucket)
    client.put_object(Bucket=job_input.bucket, Key=job_input.key, Body=b"col_a,col_b\n1,2\n")
    return ctx


@pytest.fixture
def s3_input(job_input):
    ctx = _put_source_object(job_input)
    yield
    ctx.stop()


# --- Happy path: whole path works end-to-end -----------------------------

def test_run_job_on_success_loads_rows_and_marks_the_job_succeeded(
        monkeypatch, job, job_input, s3_input, study_participant, measurement_concept):
    backend = FakeSandboxBackend(result=_success_result(_measurement_row_jsonl(study_participant, measurement_concept)))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    finished = runner.run_job(str(job.id))

    assert finished.status == ETL_JOB_STATUS_SUCCEEDED
    assert finished.started_at is not None
    assert finished.finished_at is not None
    measurement = Measurement.objects.get()
    assert measurement.person_id == study_participant.id
    assert measurement.etl_job_id == job.id


def test_run_job_on_success_enqueues_the_raw_bucket_move(
        monkeypatch, job, job_input, s3_input, study_participant, measurement_concept):
    """#163: a successful Job's inputs get moved to the raw bucket -- dispatched, not run inline,
    matching the sandbox-run task's own queue/dispatch shape."""
    from MiqaResearch.tasks.etl_orchestrator import tasks

    enqueued = []
    monkeypatch.setattr(tasks, "move_etl_job_inputs_to_raw_bucket", type("T", (), {
        "enqueue": staticmethod(lambda job_id: enqueued.append(job_id))})())
    backend = FakeSandboxBackend(result=_success_result(_measurement_row_jsonl(study_participant, measurement_concept)))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    runner.run_job(str(job.id))

    assert enqueued == [str(job.id)]


def test_run_job_on_script_failure_does_not_enqueue_a_raw_bucket_move(monkeypatch, job, job_input, s3_input):
    from MiqaResearch.tasks.etl_orchestrator import tasks

    enqueued = []
    monkeypatch.setattr(tasks, "move_etl_job_inputs_to_raw_bucket", type("T", (), {
        "enqueue": staticmethod(lambda job_id: enqueued.append(job_id))})())
    backend = FakeSandboxBackend(result=_failure_result(contract.EXIT_SCRIPT_ERROR, log=b"boom"))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    finished = runner.run_job(str(job.id))

    assert finished.status == ETL_JOB_STATUS_FAILED
    assert enqueued == []


def test_run_job_updates_job_input_sha256_and_size_from_fetched_bytes(
        monkeypatch, job, job_input, s3_input, study_participant, measurement_concept):
    backend = FakeSandboxBackend(result=_success_result(_measurement_row_jsonl(study_participant, measurement_concept)))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    runner.run_job(str(job.id))

    job_input.refresh_from_db()
    assert job_input.sha256 != ""
    assert job_input.size_bytes == len(b"col_a,col_b\n1,2\n")


def test_run_job_builds_the_spec_from_the_script_version_and_binding_config(
        monkeypatch, job, job_input, s3_input, binding, script_version, study_participant, measurement_concept):
    backend = FakeSandboxBackend(result=_success_result(_measurement_row_jsonl(study_participant, measurement_concept)))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    runner.run_job(str(job.id))

    spec = backend.received_spec
    assert spec.run_id == str(job.id)
    assert spec.image_key == script_version.image_key
    assert spec.manifest == {"datatype": "measurement", "config": {"delimiter": ","}}
    assert spec.input_files == {"export.csv": b"col_a,col_b\n1,2\n"}


def test_a_queued_job_runs_with_the_config_it_was_queued_with_even_after_the_binding_changes(
        monkeypatch, job, job_input, s3_input, binding, study_participant, measurement_concept):
    binding.config = {"delimiter": ";"}
    binding.save(update_fields=["config"])
    backend = FakeSandboxBackend(result=_success_result(_measurement_row_jsonl(study_participant, measurement_concept)))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    runner.run_job(str(job.id))

    assert backend.received_spec.manifest["config"] == {"delimiter": ","}


# --- Script-class failures: never auto-retried ----------------------------

@pytest.mark.parametrize(
    "exit_code", [contract.EXIT_SCRIPT_ERROR, contract.EXIT_CONTRACT_VIOLATION, contract.EXIT_TIMEOUT_OR_KILLED])
def test_run_job_script_class_exit_codes_fail_without_creating_a_retry(
        monkeypatch, job, job_input, s3_input, exit_code):
    backend = FakeSandboxBackend(result=_failure_result(exit_code, log=b"it went wrong"))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    finished = runner.run_job(str(job.id))

    assert finished.status == ETL_JOB_STATUS_FAILED
    assert "it went wrong" in finished.log
    assert EtlJob.objects.filter(binding=job.binding).count() == 1
    assert Measurement.objects.count() == 0


def test_run_job_caps_the_captured_log_at_64kb(monkeypatch, job, job_input, s3_input):
    huge_log = b"x" * (100 * 1024)
    backend = FakeSandboxBackend(result=_failure_result(contract.EXIT_SCRIPT_ERROR, log=huge_log))
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    finished = runner.run_job(str(job.id))

    assert len(finished.log.encode()) <= 64 * 1024


# --- Idempotency -----------------------------------------------------------

def test_run_job_is_a_no_op_for_a_job_that_is_not_pending(monkeypatch, job, job_input):
    job.status = ETL_JOB_STATUS_SUCCEEDED
    job.save()
    backend = FakeSandboxBackend()

    def _fail(*args, **kwargs):
        raise AssertionError("must not run the sandbox for an already-finished Job")

    backend.run = _fail
    monkeypatch.setattr(runner, "get_sandbox_backend", lambda: backend)

    result = runner.run_job(str(job.id))

    assert result.status == ETL_JOB_STATUS_SUCCEEDED


def _success_result(result_jsonl: bytes):
    from MiqaResearch.etl_sandbox import SandboxRunResult
    return SandboxRunResult(exit_code=contract.EXIT_SUCCESS, result_jsonl=result_jsonl, log=b"all good", killed=False)


def _failure_result(exit_code: int, *, log: bytes):
    from MiqaResearch.etl_sandbox import SandboxRunResult
    killed = exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    return SandboxRunResult(exit_code=exit_code, result_jsonl=None, log=log, killed=killed)

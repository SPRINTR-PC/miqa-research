"""ETL raw bucket move & source retention (#163): `RawBucketMover` copies a successful Job's
inputs to the raw bucket (verified by re-reading and re-hashing the copy, never trusting ETag
alone), then deletes the source. Raw-bucket keys nest by Job id so re-runs never overwrite prior
history. Within a folder-grouped Job, each input's move is independent -- one bad file's move
failure doesn't block the others (#156's own AC list).

Follows the `tests/test_dicom_storage_backend.py` (#122) precedent: moto for the fast/default
suite, exercised at the `RawBucketMover`/`move_job_inputs` seam and asserted on real bucket
contents + `EtlJobInput` state, never on internal call sequences.
"""
import hashlib

import boto3
import pytest
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from moto import mock_aws

from contract.constants.audit_log import EVENT_TYPE_ETL_SOURCE_CLEANUP_STUCK
from contract.constants.etl import (
    ETL_JOB_INPUT_SOURCE_STATUS_DELETED,
    ETL_JOB_INPUT_SOURCE_STATUS_MOVED,
    ETL_JOB_INPUT_SOURCE_STATUS_PENDING,
    ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING,
    ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK,
    ETL_JOB_STATUS_RUNNING,
    ETL_JOB_STATUS_SUCCEEDED,
    ETL_SCRIPT_ORIGIN_CUSTOM,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
)
from MiqaResearch.data.models import (
    AuditLog,
    EtlJob,
    EtlJobInput,
    EtlLocationGrant,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.tasks.etl_orchestrator import raw_bucket_mover

User = get_user_model()


@pytest.fixture(autouse=True)
def etl_s3_settings(settings):
    settings.ETL_S3_ENDPOINT_URL = None
    settings.ETL_S3_REGION_NAME = "us-east-1"
    settings.ETL_S3_ACCESS_KEY_ID = "testing"
    settings.ETL_S3_SECRET_ACCESS_KEY = "testing"
    settings.ETL_SOURCE_CLEANUP_MAX_ATTEMPTS = 3
    settings.ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS = 60
    settings.ETL_SOURCE_CLEANUP_BACKOFF_MAX_SECONDS = 3600


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Raw bucket mover test project", description="")


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
def location_grants(research_project):
    EtlLocationGrant.objects.create(project=research_project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=research_project, bucket="raw", prefix="")


@pytest.fixture
def job(binding, script_version):
    return EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED)


def _job_input(job, *, bucket="incoming", key="redcap/a.csv", data=b"data"):
    sha256 = hashlib.sha256(data).hexdigest()
    return EtlJobInput.objects.create(job=job, bucket=bucket, key=key, sha256=sha256, size_bytes=len(data))


@pytest.fixture
def s3_client():
    ctx = mock_aws()
    ctx.start()
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.create_bucket(Bucket="raw")
    yield client
    ctx.stop()


def test_a_successful_input_is_verified_and_present_in_the_raw_bucket_nested_by_job_id(
        location_grants, job, s3_client):
    data = b"raw source bytes"
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=data)
    job_input = _job_input(job, data=data)

    raw_bucket_mover.move_job_inputs(job)

    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_MOVED
    assert job_input.raw_bucket_key == f"redcap/{job.id}/a.csv"
    assert job_input.source_handled_at is not None
    stored = s3_client.get_object(Bucket="raw", Key=job_input.raw_bucket_key)
    assert stored["Body"].read() == data


def test_the_source_is_absent_after_a_successful_move(location_grants, job, s3_client):
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    _job_input(job)

    raw_bucket_mover.move_job_inputs(job)

    with pytest.raises(ClientError):
        s3_client.get_object(Bucket="incoming", Key="redcap/a.csv")


# --- Raw Retention "delete" (#246) ----------------------------------------

@pytest.fixture
def delete_job(research_project, binding, script_version):
    EtlLocationGrant.objects.create(project=research_project, bucket="incoming", prefix="")
    return EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED,
        raw_retention=PIPELINE_BINDING_RAW_RETENTION_DELETE)


def _all_keys(s3_client, bucket):
    return [obj["Key"] for obj in s3_client.list_objects_v2(Bucket=bucket).get("Contents", [])]


def test_a_delete_retention_jobs_input_is_deleted_from_the_source_without_any_raw_copy(delete_job, s3_client):
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"personnummer")
    job_input = _job_input(delete_job, data=b"personnummer")

    raw_bucket_mover.move_job_inputs(delete_job)

    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_DELETED
    assert job_input.raw_bucket_key == ""
    assert job_input.source_handled_at is not None
    assert _all_keys(s3_client, "incoming") == []
    assert _all_keys(s3_client, "raw") == []


def test_a_folder_grouped_jobs_other_inputs_still_move_when_one_input_has_no_grant_coverage(
        research_project, job, s3_client):
    # Only "incoming" is granted -- "raw" is not, so every input's move should be blocked, but
    # each independently (not one failure short-circuiting the loop over the rest).
    EtlLocationGrant.objects.create(project=research_project, bucket="incoming", prefix="")
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"aaa")
    s3_client.put_object(Bucket="incoming", Key="redcap/b.csv", Body=b"bbb")
    input_a = _job_input(job, key="redcap/a.csv", data=b"aaa")
    input_b = _job_input(job, key="redcap/b.csv", data=b"bbb")

    raw_bucket_mover.move_job_inputs(job)

    input_a.refresh_from_db()
    input_b.refresh_from_db()
    assert input_a.source_status == ETL_JOB_INPUT_SOURCE_STATUS_PENDING
    assert input_b.source_status == ETL_JOB_INPUT_SOURCE_STATUS_PENDING
    # Neither source was touched -- the ungranted raw bucket must never receive a copy either.
    assert s3_client.get_object(Bucket="incoming", Key="redcap/a.csv")["Body"].read() == b"aaa"
    assert s3_client.get_object(Bucket="incoming", Key="redcap/b.csv")["Body"].read() == b"bbb"


def test_a_folder_grouped_jobs_other_inputs_still_move_when_one_inputs_copy_is_corrupted(
        monkeypatch, location_grants, job, s3_client):
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"aaa")
    s3_client.put_object(Bucket="incoming", Key="redcap/b.csv", Body=b"bbb")
    input_a = _job_input(job, key="redcap/a.csv", data=b"aaa")
    input_b = _job_input(job, key="redcap/b.csv", data=b"corrupted-expectation")

    raw_bucket_mover.move_job_inputs(job)

    input_a.refresh_from_db()
    input_b.refresh_from_db()
    assert input_a.source_status == ETL_JOB_INPUT_SOURCE_STATUS_MOVED
    assert input_b.source_status == ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING
    # b's source is untouched -- corrupted-copy detection blocks the delete, not a silent success.
    assert s3_client.get_object(Bucket="incoming", Key="redcap/b.csv")["Body"].read() == b"bbb"


class _DeleteFailingClient:
    """Delegates everything to a real (moto-backed) client except delete_object, which always
    fails -- simulates a source that copies and verifies fine but can never be cleaned up."""

    def __init__(self, real_client):
        self._real = real_client

    def __getattr__(self, name):
        return getattr(self._real, name)

    def delete_object(self, **kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "DeleteObject")


def _admin_user(project, *, email="admin@example.com"):
    user = User.objects.create_user(username="mover-admin", email=email, password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name="Admin", defaults={"description": "Admin"})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def test_cleanup_retry_exhaustion_escalates_exactly_once_and_leaves_the_source_untouched(
        monkeypatch, settings, research_project, location_grants, job, s3_client):
    settings.ETL_SOURCE_CLEANUP_MAX_ATTEMPTS = 1
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    admin_user = _admin_user(research_project)
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    job_input = _job_input(job, data=b"data")
    monkeypatch.setattr(
        raw_bucket_mover, "build_storage_client",
        lambda storage: _DeleteFailingClient(boto3.client("s3", region_name="us-east-1")))

    raw_bucket_mover.move_job_inputs(job)

    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK
    assert s3_client.get_object(Bucket="incoming", Key="redcap/a.csv")["Body"].read() == b"data"
    assert len(mail.outbox) == 1
    assert admin_user.email in mail.outbox[0].to
    assert AuditLog.objects.filter(
        event_type=EVENT_TYPE_ETL_SOURCE_CLEANUP_STUCK, project=research_project).count() == 1

    # A stuck input is terminal -- a second sweep over the same Job must not re-send or re-record.
    raw_bucket_mover.move_job_inputs(job)

    assert len(mail.outbox) == 1
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SOURCE_CLEANUP_STUCK).count() == 1


def test_a_first_cleanup_failure_under_the_cap_schedules_a_backoff_retry_without_escalating(
        monkeypatch, settings, research_project, location_grants, job, s3_client):
    settings.ETL_SOURCE_CLEANUP_MAX_ATTEMPTS = 3
    settings.ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS = 60
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    job_input = _job_input(job, data=b"data")
    monkeypatch.setattr(
        raw_bucket_mover, "build_storage_client",
        lambda storage: _DeleteFailingClient(boto3.client("s3", region_name="us-east-1")))

    raw_bucket_mover.move_job_inputs(job)

    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING
    assert job_input.cleanup_attempts == 1
    assert job_input.cleanup_next_attempt_at is not None
    assert len(mail.outbox) == 0


# --- sweep_due_cleanups -----------------------------------------------------

def test_sweep_retries_a_due_cleanup_and_completes_the_move(location_grants, job, s3_client):
    from django.utils import timezone

    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    raw_key = f"redcap/{job.id}/a.csv"
    s3_client.put_object(Bucket="raw", Key=raw_key, Body=b"data")
    job_input = _job_input(job, data=b"data")
    job_input.raw_bucket_key = raw_key
    job_input.source_status = ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING
    job_input.cleanup_attempts = 1
    job_input.cleanup_next_attempt_at = timezone.now() - timezone.timedelta(seconds=1)
    job_input.save()

    swept = raw_bucket_mover.sweep_due_cleanups()

    assert [j.id for j in swept] == [job.id]
    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_MOVED
    with pytest.raises(ClientError):
        s3_client.get_object(Bucket="incoming", Key="redcap/a.csv")


def test_sweep_ignores_a_cleanup_not_yet_due(location_grants, job, s3_client):
    from django.utils import timezone

    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    raw_key = f"redcap/{job.id}/a.csv"
    s3_client.put_object(Bucket="raw", Key=raw_key, Body=b"data")
    job_input = _job_input(job, data=b"data")
    job_input.raw_bucket_key = raw_key
    job_input.source_status = ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING
    job_input.cleanup_attempts = 1
    job_input.cleanup_next_attempt_at = timezone.now() + timezone.timedelta(hours=1)
    job_input.save()

    swept = raw_bucket_mover.sweep_due_cleanups()

    assert swept == []
    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING


def test_a_delete_retention_jobs_failing_source_delete_escalates_with_its_retention_mode(
        monkeypatch, settings, research_project, delete_job, s3_client):
    settings.ETL_SOURCE_CLEANUP_MAX_ATTEMPTS = 1
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _admin_user(research_project)
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    job_input = _job_input(delete_job, data=b"data")
    monkeypatch.setattr(
        raw_bucket_mover, "build_storage_client",
        lambda storage: _DeleteFailingClient(boto3.client("s3", region_name="us-east-1")))

    raw_bucket_mover.move_job_inputs(delete_job)

    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK
    assert _all_keys(s3_client, "raw") == []
    assert "raw-bucket" not in mail.outbox[0].body.lower()
    event = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_SOURCE_CLEANUP_STUCK, project=research_project)
    assert event.metadata["raw_retention"] == PIPELINE_BINDING_RAW_RETENTION_DELETE


@pytest.mark.parametrize("raw_retention", ["move", PIPELINE_BINDING_RAW_RETENTION_DELETE])
def test_a_job_not_recorded_as_succeeded_never_has_its_source_touched(
        research_project, binding, script_version, location_grants, s3_client, raw_retention):
    job = EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_RUNNING, raw_retention=raw_retention)
    s3_client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"data")
    job_input = _job_input(job, data=b"data")

    raw_bucket_mover.move_job_inputs(job)

    job_input.refresh_from_db()
    assert job_input.source_status == ETL_JOB_INPUT_SOURCE_STATUS_PENDING
    assert _all_keys(s3_client, "incoming") == ["redcap/a.csv"]
    assert _all_keys(s3_client, "raw") == []

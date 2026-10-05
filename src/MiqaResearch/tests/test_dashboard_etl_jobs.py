"""View tests for the ETL Pipelines tab's Jobs section (#164): the Jobs panel lists the project's
real `EtlJob`s, a Job's detail view shows its log, inputs and pinned Script Version, and manage
roles can manually retry a failed Job. Role boundaries come from `etl_permissions` (#158) --
unit-tested in test_etl_permissions.py; this file checks the Jobs views enforce them.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_ETL_JOB_MANUAL_RETRY
from contract.constants.etl import (
    ETL_JOB_STATUS_FAILED,
    ETL_JOB_STATUS_PENDING,
    ETL_JOB_STATUS_RUNNING,
    ETL_JOB_STATUS_SUCCEEDED,
    ETL_SCRIPT_ORIGIN_NATIVE,
)
from MiqaResearch.data.models import (
    AuditLog,
    EtlJob,
    EtlJobInput,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)

User = get_user_model()

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


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


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="ETL Jobs Project", description="desc")


@pytest.fixture
def script_version(db):
    script = EtlScript.objects.create(name="Lab importer", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    return EtlScriptVersion.objects.create(
        script=script, version=3,
        source=SimpleUploadedFile("script.py", b"print()", content_type="text/x-python"), sha256="0" * 64)


@pytest.fixture
def binding(project, script_version):
    return PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix="labs/", script_version=script_version,
        raw_bucket="raw", raw_prefix="")


def _user_with_role(project, role_name):
    user = User.objects.create_user(username=f"user-{role_name.lower().replace(' ', '-')}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def _client_as(user):
    client = Client()
    client.force_login(user)
    return client


def _jobs_url(project):
    return reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=jobs"


def _detail_url(project, job):
    return reverse("dashboard_tab_etl_job_detail", args=[project.id, job.id])


def _retry_url(project, job):
    return reverse("dashboard_tab_etl_job_retry", args=[project.id, job.id])


# --- Jobs panel -----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_jobs_panel_lists_the_projects_jobs_with_their_status(project, binding, script_version):
    EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED)
    EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_FAILED)
    client = _client_as(_user_with_role(project, "PI"))

    body = client.get(_jobs_url(project), **HTMX).content.decode()

    assert "No jobs yet" not in body
    assert "Succeeded" in body
    assert "Failed" in body
    assert "incoming/labs/" in body


@pytest.mark.django_db
def test_a_running_job_past_its_timeout_and_grace_shows_as_stuck(project, binding, script_version, settings):
    settings.ETL_JOB_STUCK_GRACE_SECONDS = 60
    binding.timeout_seconds_override = 600
    binding.save()
    EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_RUNNING,
        started_at=timezone.now() - timedelta(seconds=661))
    client = _client_as(_user_with_role(project, "PI"))

    body = client.get(_jobs_url(project), **HTMX).content.decode()

    assert "Stuck" in body
    assert "Running" not in body


@pytest.mark.django_db
def test_a_running_job_within_its_timeout_shows_as_running(project, binding, script_version, settings):
    settings.ETL_JOB_STUCK_GRACE_SECONDS = 60
    binding.timeout_seconds_override = 600
    binding.save()
    EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_RUNNING,
        started_at=timezone.now() - timedelta(seconds=30))
    client = _client_as(_user_with_role(project, "PI"))

    body = client.get(_jobs_url(project), **HTMX).content.decode()

    assert "Running" in body
    assert "Stuck" not in body


# --- Job detail ---------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_jobs_detail_shows_its_log_inputs_and_pinned_script_version(project, binding, script_version):
    job = EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_FAILED,
        log="row 12: unknown concept code LBX-99")
    EtlJobInput.objects.create(job=job, bucket="incoming", key="labs/batch-7.csv", sha256="ab" * 32, size_bytes=512)
    client = _client_as(_user_with_role(project, "Investigator"))

    body = client.get(_detail_url(project, job), **HTMX).content.decode()

    assert "row 12: unknown concept code LBX-99" in body
    assert "labs/batch-7.csv" in body
    assert "ab" * 32 in body
    assert "Lab importer" in body
    assert "v3" in body


@pytest.mark.django_db
def test_another_projects_job_detail_is_404(project, script_version):
    other_project = ResearchProject.objects.create(name="Other", description="")
    other_binding = PipelineBinding.objects.create(
        project=other_project, source_bucket="elsewhere", script_version=script_version, raw_bucket="raw")
    other_job = EtlJob.objects.create(binding=other_binding, script_version=script_version)
    client = _client_as(_user_with_role(project, "Admin"))

    assert client.get(_detail_url(project, other_job), **HTMX).status_code == 404


# --- Visibility -----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ["Contributor", "Annotator"])
def test_a_role_outside_the_visible_set_gets_404_on_the_panel_and_detail(project, binding, script_version, role_name):
    job = EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_FAILED)
    client = _client_as(_user_with_role(project, role_name))

    assert client.get(_jobs_url(project), **HTMX).status_code == 404
    assert client.get(_detail_url(project, job), **HTMX).status_code == 404


# --- Manual retry ---------------------------------------------------------------------------------------------------


@pytest.fixture
def failed_job(binding, script_version):
    job = EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_FAILED, attempt=2,
        finished_at=timezone.now())
    EtlJobInput.objects.create(job=job, bucket="incoming", key="labs/batch-7.csv", sha256="ab" * 32, size_bytes=512)
    return job


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ["Admin", "Data Manager"])
def test_a_manage_role_retrying_a_failed_job_queues_a_fresh_run_of_its_pinned_version(
        project, binding, failed_job, script_version, fake_run_etl_job_task, role_name):
    # the Binding has since moved on to a newer Version -- the retry still reruns what failed
    binding.script_version = EtlScriptVersion.objects.create(
        script=script_version.script, version=4,
        source=SimpleUploadedFile("script.py", b"print(1)", content_type="text/x-python"), sha256="1" * 64)
    binding.save()
    client = _client_as(_user_with_role(project, role_name))

    response = client.post(_retry_url(project, failed_job), **HTMX)

    assert response.status_code == 200
    retry_job = EtlJob.objects.exclude(id=failed_job.id).get()
    assert retry_job.status == ETL_JOB_STATUS_PENDING
    assert retry_job.script_version == script_version
    assert retry_job.attempt == 1
    assert retry_job.retry_of is None
    assert [(i.bucket, i.key) for i in retry_job.inputs.all()] == [("incoming", "labs/batch-7.csv")]
    assert fake_run_etl_job_task.enqueued_job_ids == [str(retry_job.id)]


@pytest.mark.django_db
def test_a_manual_retry_is_audited(project, failed_job):
    user = _user_with_role(project, "Data Manager")

    _client_as(user).post(_retry_url(project, failed_job), **HTMX)

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_JOB_MANUAL_RETRY)
    assert entry.user == user
    assert entry.project == project
    assert entry.metadata["job_id"] == str(failed_job.id)


@pytest.mark.django_db
def test_a_manage_role_sees_a_retry_control_on_a_failed_job(project, failed_job):
    client = _client_as(_user_with_role(project, "Data Manager"))

    body = client.get(_detail_url(project, failed_job), **HTMX).content.decode()

    assert _retry_url(project, failed_job) in body


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ["PI", "Investigator"])
def test_a_read_only_role_sees_no_retry_control_and_cannot_post_one(
        project, failed_job, fake_run_etl_job_task, role_name):
    client = _client_as(_user_with_role(project, role_name))

    body = client.get(_detail_url(project, failed_job), **HTMX).content.decode()
    response = client.post(_retry_url(project, failed_job), **HTMX)

    assert _retry_url(project, failed_job) not in body
    assert response.status_code == 403
    assert EtlJob.objects.count() == 1
    assert fake_run_etl_job_task.enqueued_job_ids == []


@pytest.mark.django_db
def test_a_job_that_did_not_fail_cannot_be_retried(project, binding, script_version, fake_run_etl_job_task):
    job = EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED)
    client = _client_as(_user_with_role(project, "Admin"))

    body = client.post(_retry_url(project, job), **HTMX).content.decode()

    assert EtlJob.objects.count() == 1
    assert fake_run_etl_job_task.enqueued_job_ids == []
    assert "Only a failed job can be retried" in body


@pytest.mark.django_db
def test_a_retry_is_refused_while_the_binding_already_has_an_active_job(
        project, binding, script_version, failed_job, fake_run_etl_job_task):
    EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_RUNNING)
    client = _client_as(_user_with_role(project, "Admin"))

    body = client.post(_retry_url(project, failed_job), **HTMX).content.decode()

    assert EtlJob.objects.count() == 2
    assert fake_run_etl_job_task.enqueued_job_ids == []
    assert "already has a job pending or running" in body


@pytest.mark.django_db
def test_a_delete_after_load_jobs_detail_shows_its_inputs_were_deleted(project, binding, script_version):
    job = EtlJob.objects.create(
        binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED, raw_retention="delete")
    EtlJobInput.objects.create(
        job=job, bucket="incoming", key="consent/export.csv", sha256="cd" * 32, size_bytes=64,
        move_status="deleted")
    client = _client_as(_user_with_role(project, "Investigator"))

    body = client.get(_detail_url(project, job), **HTMX).content.decode()

    assert "Deleted after load" in body

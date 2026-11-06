"""Connected Storages (#394): everything a Binding/Job does against S3 -- polling, source fetch, the
raw-bucket move -- goes through that Binding's own storage, and a Location Grant only authorises
its own storage."""
import hashlib

import boto3
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from moto import mock_aws

from contract.constants.etl import ETL_JOB_STATUS_SUCCEEDED, ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    EtlJob,
    EtlJobInput,
    EtlLocationGrant,
    EtlScript,
    EtlScriptVersion,
    EtlStorage,
    PipelineBinding,
    ResearchProject,
)
from MiqaResearch.data.models.etl_storage import default_storage
from MiqaResearch.tasks.etl_orchestrator import raw_bucket_mover, runner
from MiqaResearch.tasks.etl_orchestrator.polling import poll_binding
from MiqaResearch.tasks.etl_orchestrator.s3 import EtlStorageCredentialsNotConfigured


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Storage binding project", description="")


@pytest.fixture
def script_version(project):
    script = EtlScript.objects.create(name="Importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"x"), sha256="0" * 64,
        image_key="python-etl-v1")


@pytest.fixture
def lab_storage(db):
    return EtlStorage.objects.create(
        name="Lab", endpoint_url="", region="us-east-1",
        access_key_id_env="LAB_TEST_KEY", secret_access_key_env="LAB_TEST_SECRET")


def _binding(project, script_version, storage):
    return PipelineBinding.objects.create(
        project=project, storage=storage, source_bucket="incoming", source_prefix="in/",
        script_version=script_version, raw_bucket="raw", raw_prefix="raw/")


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="incoming")
        client.create_bucket(Bucket="raw")
        yield client


def test_polling_uses_the_bindings_storage_credentials(project, script_version, lab_storage, s3, monkeypatch):
    monkeypatch.delenv("LAB_TEST_KEY", raising=False)
    monkeypatch.delenv("LAB_TEST_SECRET", raising=False)
    s3.put_object(Bucket="incoming", Key="in/a.csv", Body=b"a")

    with pytest.raises(EtlStorageCredentialsNotConfigured):
        poll_binding(_binding(project, script_version, lab_storage))


def test_polling_lists_through_a_configured_custom_storage(project, script_version, lab_storage, s3, monkeypatch):
    monkeypatch.setenv("LAB_TEST_KEY", "k")
    monkeypatch.setenv("LAB_TEST_SECRET", "s")
    s3.put_object(Bucket="incoming", Key="in/a.csv", Body=b"a")

    job = poll_binding(_binding(project, script_version, lab_storage))

    assert [i.key for i in job.inputs.all()] == ["in/a.csv"]


def test_running_a_job_fetches_through_the_bindings_storage(project, script_version, lab_storage, s3, monkeypatch):
    monkeypatch.delenv("LAB_TEST_KEY", raising=False)
    monkeypatch.delenv("LAB_TEST_SECRET", raising=False)
    binding = _binding(project, script_version, lab_storage)
    job = EtlJob.objects.create(binding=binding, script_version=script_version)
    EtlJobInput.objects.create(job=job, bucket="incoming", key="in/a.csv", sha256="", size_bytes=0)

    with pytest.raises(EtlStorageCredentialsNotConfigured):
        runner.run_job(str(job.id))


def test_a_grant_on_another_storage_does_not_authorise_the_raw_move(
        project, script_version, lab_storage, s3, monkeypatch):
    monkeypatch.setenv("LAB_TEST_KEY", "k")
    monkeypatch.setenv("LAB_TEST_SECRET", "s")
    default = default_storage()
    for bucket in ("incoming", "raw"):
        EtlLocationGrant.objects.create(project=project, storage=default, bucket=bucket, prefix="")
    binding = _binding(project, script_version, lab_storage)  # lab storage has no grants
    job = EtlJob.objects.create(binding=binding, script_version=script_version, status=ETL_JOB_STATUS_SUCCEEDED)
    s3.put_object(Bucket="incoming", Key="in/a.csv", Body=b"data")
    job_input = EtlJobInput.objects.create(
        job=job, bucket="incoming", key="in/a.csv", sha256=hashlib.sha256(b"data").hexdigest(), size_bytes=4)

    raw_bucket_mover.move_job_inputs(job)

    job_input.refresh_from_db()
    assert job_input.source_status != "moved"
    assert s3.get_object(Bucket="incoming", Key="in/a.csv")["Body"].read() == b"data"

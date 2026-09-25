"""ETL orchestrator (#162): the polling core. One poll per PipelineBinding -- list the source
bucket, diff against the EtlProcessedFile ledger, and (per the Binding's grouping_mode) either
queue a per-file Job immediately or track a folder to quiescence via EtlPendingGroup before
queueing one Job for the whole directory. At most one active Job per Binding at a time (enforced
by the DB's partial unique constraint; a second poll while one is active must not queue another).

Per #162's testing decision, these are direct calls to `poll_binding` -- no live Celery beat/worker
involved -- with ledger/Pending-Group state simulated directly (e.g. backdating
EtlPendingGroup.last_seen_at to simulate the quiescence window having elapsed).
"""
from datetime import timedelta

import boto3
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from moto import mock_aws

from contract.constants.etl import (
    ETL_JOB_STATUS_SUCCEEDED,
    ETL_SCRIPT_ORIGIN_CUSTOM,
    PIPELINE_BINDING_GROUPING_FILE,
    PIPELINE_BINDING_GROUPING_FOLDER,
)
from MiqaResearch.data.models import (
    EtlJob,
    EtlJobInput,
    EtlPendingGroup,
    EtlProcessedFile,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
)
from MiqaResearch.tasks.etl_orchestrator.polling import poll_binding


@pytest.fixture(autouse=True)
def etl_s3_settings(settings):
    settings.ETL_S3_ENDPOINT_URL = None
    settings.ETL_S3_REGION_NAME = "us-east-1"
    settings.ETL_S3_ACCESS_KEY_ID = "testing"
    settings.ETL_S3_SECRET_ACCESS_KEY = "testing"


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Polling test project", description="")


@pytest.fixture
def etl_script_version(research_project):
    script = EtlScript.objects.create(name="Importer", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"print('hi')"), sha256="0" * 64)


def _binding(research_project, etl_script_version, *, grouping_mode=PIPELINE_BINDING_GROUPING_FILE,
             quiescence_seconds=300, prefix="incoming-prefix/"):
    return PipelineBinding.objects.create(
        project=research_project, source_bucket="bucket", source_prefix=prefix,
        script_version=etl_script_version, raw_bucket="raw", raw_prefix=prefix,
        grouping_mode=grouping_mode, quiescence_seconds=quiescence_seconds,
    )


def _s3_client():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="bucket")
    return client


# --- No-op cases -------------------------------------------------------

@mock_aws
def test_poll_binding_with_an_empty_bucket_returns_none(research_project, etl_script_version):
    _s3_client()
    binding = _binding(research_project, etl_script_version)

    assert poll_binding(binding) is None
    assert EtlJob.objects.count() == 0


# --- Per-file grouping (AC #1, #3) --------------------------------------

@mock_aws
def test_file_mode_a_new_file_queues_a_job_immediately(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/a.csv", Body=b"a")
    binding = _binding(research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FILE)

    job = poll_binding(binding)

    assert job is not None
    assert job.binding_id == binding.id
    assert job.config_snapshot == binding.config
    assert list(EtlJobInput.objects.filter(job=job).values_list("bucket", "key")) == [
        ("bucket", "incoming-prefix/a.csv")]
    assert EtlProcessedFile.objects.filter(binding=binding, key="incoming-prefix/a.csv").exists()


@mock_aws
def test_file_mode_a_second_poll_with_another_new_file_does_not_queue_while_a_job_is_active(
        research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/a.csv", Body=b"a")
    binding = _binding(research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FILE)
    first_job = poll_binding(binding)
    assert first_job is not None

    client.put_object(Bucket="bucket", Key="incoming-prefix/b.csv", Body=b"b")
    second_result = poll_binding(binding)

    assert second_result is None
    assert EtlJob.objects.filter(binding=binding).count() == 1
    # The second file was still recorded to the ledger -- it isn't lost, just not yet queued.
    assert EtlProcessedFile.objects.filter(binding=binding, key="incoming-prefix/b.csv").exists()
    assert not EtlJobInput.objects.filter(job__binding=binding, key="incoming-prefix/b.csv").exists()


@mock_aws
def test_file_mode_queues_the_waiting_file_once_the_active_job_is_no_longer_active(
        research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/a.csv", Body=b"a")
    binding = _binding(research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FILE)
    first_job = poll_binding(binding)
    client.put_object(Bucket="bucket", Key="incoming-prefix/b.csv", Body=b"b")
    poll_binding(binding)  # recorded but not queued, per the previous test

    first_job.status = ETL_JOB_STATUS_SUCCEEDED
    first_job.save()
    second_job = poll_binding(binding)

    assert second_job is not None
    assert second_job.pk != first_job.pk
    assert list(EtlJobInput.objects.filter(job=second_job).values_list("key", flat=True)) == ["incoming-prefix/b.csv"]


@mock_aws
def test_a_file_already_assigned_to_any_job_is_never_requeued_by_a_later_poll(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/a.csv", Body=b"a")
    binding = _binding(research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FILE)
    first_job = poll_binding(binding)
    first_job.status = ETL_JOB_STATUS_SUCCEEDED
    first_job.save()

    # Object still sits in the bucket (source retention isn't #162's concern); polling again
    # must not create a second Job for the same file.
    second_result = poll_binding(binding)

    assert second_result is None
    assert EtlJob.objects.filter(binding=binding).count() == 1


# --- Folder grouping + quiescence (AC #2) -------------------------------

@mock_aws
def test_folder_mode_does_not_queue_before_the_quiescence_window_elapses(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/2026-09-01/a.csv", Body=b"a")
    binding = _binding(
        research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FOLDER,
        quiescence_seconds=300)

    result = poll_binding(binding)

    assert result is None
    assert EtlJob.objects.count() == 0
    group = EtlPendingGroup.objects.get(binding=binding, group_key="2026-09-01")
    assert group.last_seen_at is not None


@mock_aws
def test_folder_mode_queues_every_file_in_the_group_once_quiescent(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/2026-09-01/a.csv", Body=b"a")
    client.put_object(Bucket="bucket", Key="incoming-prefix/2026-09-01/b.csv", Body=b"b")
    binding = _binding(
        research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FOLDER,
        quiescence_seconds=300)
    poll_binding(binding)  # discovers both files, starts the quiescence window
    EtlPendingGroup.objects.filter(binding=binding, group_key="2026-09-01").update(
        last_seen_at=timezone.now() - timedelta(seconds=301))

    job = poll_binding(binding)

    assert job is not None
    assert sorted(EtlJobInput.objects.filter(job=job).values_list("key", flat=True)) == [
        "incoming-prefix/2026-09-01/a.csv", "incoming-prefix/2026-09-01/b.csv",
    ]
    assert not EtlPendingGroup.objects.filter(binding=binding, group_key="2026-09-01").exists()


@mock_aws
def test_folder_mode_a_new_file_resets_the_quiescence_window(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/2026-09-01/a.csv", Body=b"a")
    binding = _binding(
        research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FOLDER,
        quiescence_seconds=300)
    poll_binding(binding)
    EtlPendingGroup.objects.filter(binding=binding, group_key="2026-09-01").update(
        last_seen_at=timezone.now() - timedelta(seconds=301))

    # A new file lands in the same folder just before the (already-passed) quiescence check.
    client.put_object(Bucket="bucket", Key="incoming-prefix/2026-09-01/b.csv", Body=b"b")
    result = poll_binding(binding)

    assert result is None
    assert EtlJob.objects.count() == 0
    group = EtlPendingGroup.objects.get(binding=binding, group_key="2026-09-01")
    assert timezone.now() - group.last_seen_at < timedelta(seconds=5)


@mock_aws
def test_folder_mode_groups_two_different_directories_independently(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/dir-a/x.csv", Body=b"x")
    client.put_object(Bucket="bucket", Key="incoming-prefix/dir-b/y.csv", Body=b"y")
    binding = _binding(
        research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FOLDER,
        quiescence_seconds=300)
    poll_binding(binding)
    EtlPendingGroup.objects.filter(binding=binding, group_key="dir-a").update(
        last_seen_at=timezone.now() - timedelta(seconds=301))
    # dir-b stays fresh (not quiescent yet).

    job = poll_binding(binding)

    assert job is not None
    assert list(EtlJobInput.objects.filter(job=job).values_list("key", flat=True)) == ["incoming-prefix/dir-a/x.csv"]
    assert EtlPendingGroup.objects.filter(binding=binding, group_key="dir-b").exists()


@mock_aws
def test_folder_mode_files_directly_under_the_prefix_group_under_the_root(research_project, etl_script_version):
    client = _s3_client()
    client.put_object(Bucket="bucket", Key="incoming-prefix/flat.csv", Body=b"x")
    binding = _binding(
        research_project, etl_script_version, grouping_mode=PIPELINE_BINDING_GROUPING_FOLDER,
        quiescence_seconds=300)

    poll_binding(binding)

    assert EtlPendingGroup.objects.get(binding=binding).group_key == ""

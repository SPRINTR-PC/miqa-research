"""Writes for the ETL Jobs section (#164): manually retry a failed EtlJob.

A manual retry is a fresh run, not an auto-retry: a new EtlJob with `attempt=1` and no `retry_of`
(that link is reserved for the orchestrator's capped infra-class retries, #162), rerunning the
failed Job's own pinned Script Version -- not whatever the Binding points at now -- over the same
inputs. Like an auto-retry, it's refused while the Binding already has an active Job (the partial
unique index on EtlJob holds either way).
"""
from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction

from contract.constants.audit_log import EVENT_TYPE_ETL_JOB_MANUAL_RETRY
from contract.constants.etl import ETL_JOB_STATUS_FAILED
from MiqaResearch.data.models import EtlJob, EtlJobInput

from .audit import record_etl_event
from .exceptions import EtlJobStateError

_ACTIVE_JOB_MESSAGE = "This binding already has a job pending or running; retry once it finishes."


async def retry_failed_job(*, project, user, request, job: EtlJob) -> EtlJob:
    if job.status != ETL_JOB_STATUS_FAILED:
        raise EtlJobStateError("Only a failed job can be retried.")

    retry_job = await sync_to_async(_create_manual_retry)(job)

    from MiqaResearch.tasks.etl_orchestrator import tasks
    tasks.run_etl_job.enqueue(str(retry_job.id))

    await record_etl_event(
        EVENT_TYPE_ETL_JOB_MANUAL_RETRY, user=user, request=request, project=project,
        metadata={"job_id": str(job.id), "retry_job_id": str(retry_job.id), "binding_id": str(job.binding_id)},
    )
    return retry_job


def _create_manual_retry(job: EtlJob) -> EtlJob:
    try:
        with transaction.atomic():
            retry_job = EtlJob.objects.create(
                binding_id=job.binding_id, script_version_id=job.script_version_id, config_snapshot=job.config_snapshot,
            )
            EtlJobInput.objects.bulk_create([
                EtlJobInput(job=retry_job, bucket=job_input.bucket, key=job_input.key, sha256="", size_bytes=0)
                for job_input in job.inputs.all()
            ])
    except IntegrityError:
        raise EtlJobStateError(_ACTIVE_JOB_MESSAGE)
    return retry_job

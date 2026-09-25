"""ETL orchestrator (#162): Celery task entry points. Each is a thin wrapper -- id resolution and
dispatch in, the real logic delegated to this package's other modules -- matching the DICOM
ingestion task precedent (tasks/dicom_handling/tasks.py). Per #162's testing decision, every test
calls these via `.func(...)` directly rather than through real Celery beat/dispatch.
"""
from django.tasks import task

from contract.constants.celery import QUEUE_ETL_POLL, QUEUE_ETL_RUN
from MiqaResearch.data.models import EtlJob, PipelineBinding

from . import log_retention, polling, raw_bucket_mover, runner, stuck


@task(queue_name=QUEUE_ETL_POLL)
def fan_out_etl_polls() -> dict:
    """Celery-beat-scheduled (every MIRES_ETL_POLL_INTERVAL_SECONDS): one poll per Binding."""
    binding_ids = list(PipelineBinding.objects.values_list("id", flat=True))
    for binding_id in binding_ids:
        poll_pipeline_binding.enqueue(str(binding_id))
    return {"bindings_polled": len(binding_ids)}


@task(queue_name=QUEUE_ETL_POLL)
def poll_pipeline_binding(binding_id: str) -> dict:
    binding = PipelineBinding.objects.get(pk=binding_id)
    job = polling.poll_binding(binding)
    if job is not None:
        run_etl_job.enqueue(str(job.id))
    return {"job_id": str(job.id) if job is not None else None}


@task(queue_name=QUEUE_ETL_RUN)
def run_etl_job(job_id: str) -> dict:
    job = runner.run_job(job_id)
    return {"job_id": str(job.id), "status": job.status}


@task(queue_name=QUEUE_ETL_RUN)
def move_etl_job_inputs_to_raw_bucket(job_id: str) -> dict:
    """#163: dispatched by runner._finalize on a successful EtlJob."""
    job = EtlJob.objects.select_related("binding__project").get(pk=job_id)
    raw_bucket_mover.move_job_inputs(job)
    return {"job_id": str(job.id)}


@task(queue_name=QUEUE_ETL_POLL)
def recover_stuck_etl_jobs() -> dict:
    recovered = stuck.recover_stuck_jobs()
    return {"recovered": len(recovered)}


@task(queue_name=QUEUE_ETL_POLL)
def prune_etl_job_logs() -> dict:
    pruned = log_retention.prune_logs()
    return {"pruned": pruned}


@task(queue_name=QUEUE_ETL_POLL)
def retry_etl_source_cleanup() -> dict:
    swept = raw_bucket_mover.sweep_due_cleanups()
    return {"jobs_swept": len(swept)}

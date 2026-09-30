"""ETL orchestrator (#225): periodic removal of orphaned sandboxes. A `QUEUE_ETL_RUN` worker that
dies mid-run never reaches its backend's own cleanup, so its container (or K8s Job/pods/PVC) is
left behind. Stuck-job recovery (stuck.py) fails and retries the EtlJob; this sweep removes the
sandbox itself.

A sandbox is live exactly while its EtlJob is pending or running -- the runner marks a Job
running before starting its sandbox, and the backend removes the sandbox before the Job is
finalized. A stuck Job's sandbox is therefore kept until stuck recovery fails the Job, and swept
on the next pass after that.
"""
from contract.constants.etl import ETL_JOB_STATUS_PENDING, ETL_JOB_STATUS_RUNNING
from MiqaResearch.data.models import EtlJob
from MiqaResearch.etl_sandbox import get_sandbox_backend


def sweep_orphaned_sandboxes() -> None:
    get_sandbox_backend().sweep(live_run_ids=_live_run_ids)


def _live_run_ids() -> set[str]:
    job_ids = EtlJob.objects.filter(
        status__in=[ETL_JOB_STATUS_PENDING, ETL_JOB_STATUS_RUNNING]).values_list("id", flat=True)
    return {str(job_id) for job_id in job_ids}

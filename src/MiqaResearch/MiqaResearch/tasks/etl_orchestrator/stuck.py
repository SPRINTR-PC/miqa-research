"""ETL orchestrator (#162): stuck-Job recovery. No heartbeat mechanism -- a Job stuck in
"running" past its own resolved sandbox timeout plus a grace period (MIRES_ETL_JOB_STUCK_GRACE_SECONDS)
is assumed to have lost its worker (crashed, OOM-killed, node evicted, ...) and is recovered via
the same infra-class retry path a SandboxBackend.run() connectivity failure takes (retry.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from contract.constants.etl import ETL_JOB_STATUS_RUNNING
from MiqaResearch.data.models import EtlJob
from MiqaResearch.etl_sandbox import resolve_limits

from . import retry


def is_stuck(job: EtlJob, now: datetime) -> bool:
    """Whether `job` is "running" past its own resolved sandbox timeout plus the grace period.
    Needs `job.binding` loaded; runs no query itself, so the Jobs panel (#164) can call it too."""
    from django.conf import settings

    if job.status != ETL_JOB_STATUS_RUNNING or job.started_at is None:
        return False
    grace = timedelta(seconds=settings.ETL_JOB_STUCK_GRACE_SECONDS)
    deadline = job.started_at + timedelta(seconds=resolve_limits(job.binding).timeout_seconds) + grace
    return now >= deadline


def find_stuck_jobs() -> list[EtlJob]:
    now = timezone.now()
    return [
        job for job in EtlJob.objects.filter(status=ETL_JOB_STATUS_RUNNING).select_related("binding")
        if is_stuck(job, now)
    ]


def recover_stuck_jobs() -> list[EtlJob]:
    recovered = []
    for job in find_stuck_jobs():
        retry.retry_infra_failure(job, reason="worker vanished mid-run (stuck-job timeout+grace exceeded)")
        recovered.append(job)
    return recovered

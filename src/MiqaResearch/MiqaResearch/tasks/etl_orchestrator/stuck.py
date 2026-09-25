"""ETL orchestrator (#162): stuck-Job recovery. No heartbeat mechanism -- a Job stuck in
"running" past its own resolved sandbox timeout plus a grace period (MIRES_ETL_JOB_STUCK_GRACE_SECONDS)
is assumed to have lost its worker (crashed, OOM-killed, node evicted, ...) and is recovered via
the same infra-class retry path a SandboxBackend.run() connectivity failure takes (retry.py).
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from contract.constants.etl import ETL_JOB_STATUS_RUNNING
from MiqaResearch.data.models import EtlJob
from MiqaResearch.etl_sandbox import resolve_limits

from . import retry


def find_stuck_jobs() -> list[EtlJob]:
    from django.conf import settings

    now = timezone.now()
    grace = timedelta(seconds=settings.ETL_JOB_STUCK_GRACE_SECONDS)
    stuck_jobs = []
    for job in EtlJob.objects.filter(status=ETL_JOB_STATUS_RUNNING).select_related("binding"):
        if job.started_at is None:
            continue
        limits = resolve_limits(job.binding)
        deadline = job.started_at + timedelta(seconds=limits.timeout_seconds) + grace
        if now >= deadline:
            stuck_jobs.append(job)
    return stuck_jobs


def recover_stuck_jobs() -> list[EtlJob]:
    recovered = []
    for job in find_stuck_jobs():
        retry.retry_infra_failure(job, reason="worker vanished mid-run (stuck-job timeout+grace exceeded)")
        recovered.append(job)
    return recovered

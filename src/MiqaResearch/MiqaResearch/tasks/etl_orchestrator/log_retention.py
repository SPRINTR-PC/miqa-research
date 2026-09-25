"""ETL orchestrator (#162): daily log-retention prune. EtlJob.log is already capped at 64 KB per
run by the runner; this additionally clears it once a Job is older than the effective retention
window -- logs stay available long enough to debug a recent failure without growing unbounded.
"""
from datetime import timedelta

from django.utils import timezone

from MiqaResearch.data.models import EtlJob
from MiqaResearch.data.models.etl_project_settings import get_log_retention_days


def prune_logs() -> int:
    pruned = 0
    for job in EtlJob.objects.exclude(log="").select_related("binding__project"):
        reference = job.finished_at or job.created_at
        retention_days = get_log_retention_days(job.binding.project)
        cutoff = timezone.now() - timedelta(days=retention_days)
        if reference < cutoff:
            job.log = ""
            job.save(update_fields=["log"])
            pruned += 1
    return pruned

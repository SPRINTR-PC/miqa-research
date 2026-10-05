"""ETL orchestrator (#162): failure classification + capped auto-retry.

Only a runner-level problem meaning no container was ever started counts as infra-class and gets
an automatic, capped retry (a fresh EtlJob attempt) -- e.g. the configured SandboxBackend being
unreachable, or (for stuck-job recovery, stuck.py) its worker vanishing mid-run with no heartbeat
to report otherwise. A config-class runner error (UnknownSandboxImage, SandboxInputTooLarge) is a
Binding/Script misconfiguration a retry can never fix, so it always fails permanently for manual
review -- as does every script-class outcome (a completed run reporting a non-zero exit code):
none of exit 1/2/3 auto-retries, per #156's own spec text ("script error, contract violation,
timeout" are grouped explicitly under "everything else... requires manual retry").
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from contract.constants.etl import ETL_JOB_STATUS_FAILED
from MiqaResearch.data.models import EtlJob, EtlJobInput
from MiqaResearch.etl_sandbox import SandboxInputTooLarge, UnknownSandboxImage

_NON_RETRYABLE_EXCEPTIONS = (UnknownSandboxImage, SandboxInputTooLarge)


def fail_job(job: EtlJob, *, reason: str) -> None:
    job.status = ETL_JOB_STATUS_FAILED
    job.finished_at = job.finished_at or timezone.now()
    job.log = (f"{job.log}\n[orchestrator] {reason}" if job.log else f"[orchestrator] {reason}")
    job.save(update_fields=["status", "finished_at", "log"])


def handle_run_exception(job: EtlJob, exc: Exception) -> EtlJob | None:
    """`exc` is what SandboxBackend.run() itself raised (no container was ever started). Fails
    `job` permanently for a config-class exception; otherwise treats it as infra-class and queues
    a capped auto-retry. Returns the new retry EtlJob, or None if none was queued."""
    if isinstance(exc, _NON_RETRYABLE_EXCEPTIONS):
        fail_job(job, reason=f"sandbox rejected the run before starting: {exc}")
        return None
    return retry_infra_failure(job, reason=f"sandbox backend unreachable: {exc}")


def retry_infra_failure(job: EtlJob, *, reason: str) -> EtlJob | None:
    from django.conf import settings

    fail_job(job, reason=reason)
    if job.attempt >= settings.ETL_JOB_MAX_AUTO_RETRIES:
        return None
    return _create_retry(job)


def _create_retry(job: EtlJob) -> EtlJob | None:
    try:
        with transaction.atomic():
            retry_job = EtlJob.objects.create(
                binding=job.binding, script_version=job.script_version, attempt=job.attempt + 1,
                retry_of=job, config_snapshot=job.config_snapshot, raw_retention=job.raw_retention,
            )
            EtlJobInput.objects.bulk_create([
                EtlJobInput(job=retry_job, bucket=job_input.bucket, key=job_input.key, sha256="", size_bytes=0)
                for job_input in job.inputs.all()
            ])
    except IntegrityError:
        # Binding already has another active Job (race) -- `job` is already permanently failed
        # (fail_job, above) for manual retry; there's nothing more to do here.
        return None

    from .tasks import run_etl_job
    run_etl_job.enqueue(str(retry_job.id))
    return retry_job

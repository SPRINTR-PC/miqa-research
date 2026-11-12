"""ETL raw bucket move & source retention (#163): on a successful `EtlJob`, moves each handled
input from its source bucket to the Binding's raw bucket -- or, for a Job whose Raw Retention
snapshot is "delete" (#246, ADR 0032), only deletes the source, with no copy anywhere.
Move = copy with a SHA-256 checksum, then verify size and hash against the copy (never trusting
ETag alone), then delete the source.
Raw-bucket keys nest by Job id, so re-runs never overwrite prior history.

Plain boto3 against the Binding's own Connected Storage (#394; client built by
`s3.build_storage_client`, independent of the sandbox runner's/DICOM pipeline's own S3 wrappers),
with per-project bucket isolation enforced in application code via `location_grant_allows`
(readers/etl_reader.py) -- not per-project RustFS IAM. Within a folder-grouped Job, each input's
move is independent: one bad file's move failure doesn't block the others.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_ETL_SOURCE_CLEANUP_STUCK
from contract.constants.etl import (
    ETL_JOB_INPUT_SOURCE_STATUS_DELETED,
    ETL_JOB_INPUT_SOURCE_STATUS_KEPT_IN_SOURCE,
    ETL_JOB_INPUT_SOURCE_STATUS_MOVED,
    ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING,
    ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK,
    ETL_JOB_STATUS_SUCCEEDED,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
)
from contract.constants.research_project_role import PROJECT_ROLE_ADMIN, PROJECT_ROLE_DATA_MANAGER
from MiqaResearch.data.models import AuditLog, EtlJob, EtlJobInput, EtlLocationGrant
from MiqaResearch.readers.etl_reader import location_grant_allows
from MiqaResearch.tasks.etl_orchestrator.s3 import build_storage_client

User = get_user_model()


class RawBucketMoveError(Exception):
    """One input's move could not complete this attempt. Callers scope this to the one
    EtlJobInput being moved -- another input's move within the same Job is unaffected."""


class _GrantDeniedError(RawBucketMoveError):
    """The move falls outside this project's EtlLocationGrants -- a Binding/grant
    misconfiguration no amount of retrying will fix, so it never enters the capped-backoff
    cleanup-retry path (unlike a copy/verify/delete failure)."""


def move_job_inputs(job: EtlJob) -> None:
    """Attempts to move every not-yet-moved input of `job` to its Binding's raw bucket. Each
    input's move is independent: one raising doesn't stop the others. A Job not recorded as
    succeeded is left alone -- under "delete" Raw Retention its source would otherwise be lost."""
    if job.status != ETL_JOB_STATUS_SUCCEEDED:
        return
    binding = job.binding
    grants = list(EtlLocationGrant.objects.filter(project_id=binding.project_id, storage_id=binding.storage_id))
    client = build_storage_client(binding.storage)

    terminal_statuses = (
        ETL_JOB_INPUT_SOURCE_STATUS_MOVED, ETL_JOB_INPUT_SOURCE_STATUS_DELETED,
        ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK, ETL_JOB_INPUT_SOURCE_STATUS_KEPT_IN_SOURCE)
    for job_input in job.inputs.exclude(source_status__in=terminal_statuses):
        try:
            _move_one(client, grants, binding, job, job_input)
        except _GrantDeniedError:
            continue
        except RawBucketMoveError:
            _record_cleanup_failure(job_input)
            continue


def sweep_due_cleanups() -> list[EtlJob]:
    """Retries every EtlJobInput whose capped-backoff source-cleanup retry is due, one
    `move_job_inputs` pass per distinct Job. Returns the Jobs swept."""
    due_job_ids = EtlJobInput.objects.filter(
        source_status=ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING,
        cleanup_next_attempt_at__lte=timezone.now(),
    ).values_list("job_id", flat=True).distinct()
    jobs = list(EtlJob.objects.filter(pk__in=due_job_ids).select_related("binding__project"))
    for job in jobs:
        move_job_inputs(job)
    return jobs


def _move_one(client, grants, binding, job: EtlJob, job_input: EtlJobInput) -> None:
    if not location_grant_allows(grants, job_input.bucket, job_input.key):
        raise _GrantDeniedError(
            f"source {job_input.bucket}/{job_input.key} falls outside this project's EtlLocationGrants")

    if job.raw_retention == PIPELINE_BINDING_RAW_RETENTION_DELETE:
        _delete_source(client, job_input, done_status=ETL_JOB_INPUT_SOURCE_STATUS_DELETED)
        return

    raw_key = f"{binding.raw_prefix}{job.id}/{_relative_key(binding, job_input.key)}"
    if not location_grant_allows(grants, binding.raw_bucket, raw_key):
        raise _GrantDeniedError(
            f"move of {job_input.bucket}/{job_input.key} -> {binding.raw_bucket}/{raw_key} "
            f"falls outside this project's EtlLocationGrants")

    if not job_input.raw_bucket_key:
        _copy_and_verify(client, binding, job_input, raw_key)

    _delete_source(client, job_input, done_status=ETL_JOB_INPUT_SOURCE_STATUS_MOVED)


def _copy_and_verify(client, binding, job_input: EtlJobInput, raw_key: str) -> None:
    try:
        client.copy_object(
            Bucket=binding.raw_bucket, Key=raw_key,
            CopySource={"Bucket": job_input.bucket, "Key": job_input.key})
        copied = client.get_object(Bucket=binding.raw_bucket, Key=raw_key)
        copied_bytes = copied["Body"].read()
    except ClientError as exc:
        raise RawBucketMoveError(f"copy failed for {job_input.bucket}/{job_input.key}") from exc

    if len(copied_bytes) != job_input.size_bytes or hashlib.sha256(copied_bytes).hexdigest() != job_input.sha256:
        try:
            client.delete_object(Bucket=binding.raw_bucket, Key=raw_key)
        except ClientError:
            pass  # best-effort cleanup of the corrupt copy; the real failure is raised below
        raise RawBucketMoveError(f"copy of {job_input.bucket}/{job_input.key} failed size/hash verification")

    job_input.raw_bucket_key = raw_key
    job_input.save(update_fields=["raw_bucket_key"])


def _delete_source(client, job_input: EtlJobInput, *, done_status: str) -> None:
    try:
        client.delete_object(Bucket=job_input.bucket, Key=job_input.key)
    except ClientError as exc:
        raise RawBucketMoveError(f"source delete failed for {job_input.bucket}/{job_input.key}") from exc

    job_input.source_status = done_status
    job_input.source_handled_at = timezone.now()
    job_input.save(update_fields=["source_status", "source_handled_at"])


def _record_cleanup_failure(job_input: EtlJobInput) -> None:
    """A copy/verify/delete attempt failed (as opposed to a grant denial). Capped-backoff retry:
    on cap exhaustion, escalate and leave the input `source_cleanup_stuck` for manual handling."""
    from django.conf import settings

    job_input.cleanup_attempts += 1
    if job_input.cleanup_attempts >= settings.ETL_SOURCE_CLEANUP_MAX_ATTEMPTS:
        job_input.source_status = ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK
        job_input.cleanup_next_attempt_at = None
        job_input.save(update_fields=["source_status", "cleanup_attempts", "cleanup_next_attempt_at"])
        _escalate_stuck_cleanup(job_input)
        return

    delay_seconds = min(
        settings.ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS * (2 ** (job_input.cleanup_attempts - 1)),
        settings.ETL_SOURCE_CLEANUP_BACKOFF_MAX_SECONDS,
    )
    job_input.source_status = ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING
    job_input.cleanup_next_attempt_at = timezone.now() + timedelta(seconds=delay_seconds)
    job_input.save(update_fields=["source_status", "cleanup_attempts", "cleanup_next_attempt_at"])


def _escalate_stuck_cleanup(job_input: EtlJobInput) -> None:
    """Fires once, guaranteed by the caller never re-selecting a `source_cleanup_stuck` input:
    a one-time email to staff/Admin/Data-Manager plus an `etl_source_cleanup_stuck` audit event.
    The source file itself is left untouched for manual handling."""
    from django.conf import settings

    project = job_input.job.binding.project
    recipients = set(User.objects.filter(is_staff=True).exclude(email="").values_list("email", flat=True))
    recipients |= set(
        User.objects.filter(
            researchprojectuserrolemap__project=project,
            researchprojectuserrolemap__role__name__in=[PROJECT_ROLE_ADMIN, PROJECT_ROLE_DATA_MANAGER],
        ).exclude(email="").values_list("email", flat=True)
    )
    if recipients:
        send_mail(
            subject="MiqaResearch: ETL source cleanup stuck",
            message=(
                f"An ETL source file for project {project.name!r} could not be deleted after a "
                f"successful load ({job_input.cleanup_attempts} attempts) and needs manual handling. "
                f"Job {job_input.job_id}, input {job_input.id}."
            ),
            from_email=settings.NO_REPLY_EMAIL_ADDRESS,
            recipient_list=sorted(recipients),
        )

    AuditLog.objects.record(
        EVENT_TYPE_ETL_SOURCE_CLEANUP_STUCK, project=project,
        metadata={
            "job_id": str(job_input.job_id), "job_input_id": str(job_input.id),
            "raw_retention": job_input.job.raw_retention,
        })


def _relative_key(binding, key: str) -> str:
    prefix = binding.source_prefix
    relative = key[len(prefix):] if key.startswith(prefix) else key
    return relative.lstrip("/")

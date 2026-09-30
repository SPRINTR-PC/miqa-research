"""The ETL orchestrator's polling core (#162): one poll per `PipelineBinding` -- a full bucket
re-list diffed against the `EtlProcessedFile` ledger (never bucket events). A per-file Binding
queues its oldest unqueued file immediately; a folder-grouped Binding tracks each immediate child
directory to quiescence via a persisted `EtlPendingGroup` before queueing one Job for the whole
directory. Exactly one active Job per Binding at a time -- enforced by the DB's partial unique
constraint (`mires_etl_job_one_active_per_binding`), caught here as a plain "not queued this poll"
result rather than an error, since a busy Binding is the normal case, not a fault.

A file is "unassigned" (still a queueing candidate) exactly when its (bucket, key) has never
appeared in any EtlJobInput for this Binding -- once assigned to a Job, its fate belongs to that
Job's own retry policy, never to a later poll.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from contract.constants.etl import PIPELINE_BINDING_GROUPING_FOLDER
from MiqaResearch.data.models import EtlJob, EtlJobInput, EtlPendingGroup, EtlProcessedFile

from .s3 import EtlBucketSource


def poll_binding(binding) -> EtlJob | None:
    """Poll `binding`'s source bucket once. Returns the EtlJob queued this poll, or None if
    nothing was queued (nothing new/quiescent yet, or the Binding already has an active Job)."""
    source = EtlBucketSource(binding.source_bucket, binding.source_prefix)
    new_files = _record_new_files(binding, source.list_objects())

    if binding.grouping_mode == PIPELINE_BINDING_GROUPING_FOLDER:
        return _poll_folder_grouped(binding, new_files)
    return _poll_per_file(binding)


def rehome_backlog_after_grouping_change(binding) -> None:
    """#224: re-derive `binding`'s pending folder groups after its grouping mode was edited. Folder
    polling only ever tracks *newly* seen files, so without this, files already in the ledger but
    not yet queued would be stranded by a switch to folder grouping. Their groups start a fresh
    quiescence window now. A switch to per-file just drops the groups -- per-file polling queues
    every unassigned file on its own."""
    EtlPendingGroup.objects.filter(binding=binding).delete()
    if binding.grouping_mode == PIPELINE_BINDING_GROUPING_FOLDER:
        backlog = list(_unassigned_files(binding))
        if backlog:
            _touch_pending_groups(binding, backlog)


def _poll_per_file(binding) -> EtlJob | None:
    files = list(_unassigned_files(binding)[:1])
    if not files:
        return None
    return _create_job(binding, files)


def _poll_folder_grouped(binding, new_files: list[EtlProcessedFile]) -> EtlJob | None:
    if new_files:
        _touch_pending_groups(binding, new_files)

    for group_key in _quiescent_group_keys(binding):
        files = _files_in_group(binding, group_key)
        if not files:
            EtlPendingGroup.objects.filter(binding=binding, group_key=group_key).delete()
            continue
        job = _create_job(binding, files)
        if job is None:
            # Binding already has an active Job (from this or another group) -- leave the
            # pending group as-is, it's still quiescent and will be retried next poll.
            return None
        EtlPendingGroup.objects.filter(binding=binding, group_key=group_key).delete()
        return job
    return None


def _record_new_files(binding, object_refs) -> list[EtlProcessedFile]:
    existing_keys = set(EtlProcessedFile.objects.filter(binding=binding).values_list("key", flat=True))
    created = []
    for ref in object_refs:
        if ref.key in existing_keys:
            continue
        try:
            with transaction.atomic():
                processed = EtlProcessedFile.objects.create(
                    binding=binding, bucket=ref.bucket, key=ref.key,
                    etag=ref.etag, last_modified=ref.last_modified)
        except IntegrityError:
            # Another concurrent poll of this same Binding recorded it first -- not a new file.
            continue
        created.append(processed)
    return created


def _unassigned_files(binding):
    assigned_keys = EtlJobInput.objects.filter(job__binding=binding).values_list("key", flat=True)
    return (
        EtlProcessedFile.objects.filter(binding=binding)
        .exclude(key__in=assigned_keys)
        .order_by("first_seen_at")
    )


def _group_key_for(binding, key: str) -> str:
    prefix = binding.source_prefix
    relative = key[len(prefix):] if key.startswith(prefix) else key
    relative = relative.lstrip("/")
    if "/" in relative:
        return relative.split("/", 1)[0]
    return ""


def _touch_pending_groups(binding, new_files: list[EtlProcessedFile]) -> None:
    now = timezone.now()
    group_keys = {_group_key_for(binding, pf.key) for pf in new_files}
    for group_key in group_keys:
        EtlPendingGroup.objects.update_or_create(
            binding=binding, group_key=group_key, defaults={"last_seen_at": now})


def _quiescent_group_keys(binding) -> list[str]:
    cutoff = timezone.now() - timedelta(seconds=binding.quiescence_seconds)
    return list(
        EtlPendingGroup.objects.filter(binding=binding, last_seen_at__lte=cutoff)
        .order_by("last_seen_at")
        .values_list("group_key", flat=True)
    )


def _files_in_group(binding, group_key: str) -> list[EtlProcessedFile]:
    return [pf for pf in _unassigned_files(binding) if _group_key_for(binding, pf.key) == group_key]


def _create_job(binding, processed_files: list[EtlProcessedFile]) -> EtlJob | None:
    try:
        with transaction.atomic():
            job = EtlJob.objects.create(
                binding=binding, script_version=binding.script_version, config_snapshot=binding.config)
            EtlJobInput.objects.bulk_create([
                EtlJobInput(job=job, bucket=pf.bucket, key=pf.key, sha256="", size_bytes=0)
                for pf in processed_files
            ])
    except IntegrityError:
        # The partial unique constraint: binding already has an active (pending/running) Job.
        return None
    return job

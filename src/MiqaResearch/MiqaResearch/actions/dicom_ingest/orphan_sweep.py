"""Orphan DICOM blob sweep (#420, design on #407).

An orphan is a blob under `DICOM/` with no `DicomFile` row whose `file` equals its key (a crash before
rollback, a failed on_commit discard, a deleted row). Age is the storage `LastModified`.

- reportable: older than DICOM_ORPHAN_DETECT_HOURS.
- deletable: older than DICOM_ORPHAN_GRACE_HOURS *and* already reportable at the previous run (taken
  from the last `dicom_orphan_sweep` audit event), so nothing is deleted without an earlier notified
  run; the first run ever deletes nothing.
- circuit breaker: a deletable set above DICOM_ORPHAN_MAX_DELETE_COUNT or MAX_DELETE_FRACTION of listed
  blobs deletes nothing unless forced (a restored database makes every blob look orphaned).

No PHI: only blob keys (UUIDs and dates), counts and byte totals reach the log, email and audit event.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_DICOM_ORPHAN_SWEEP
from MiqaResearch.data.models import AuditLog, DicomFile
from MiqaResearch.data.models.dicom_storage import DicomStorage

logger = logging.getLogger(__name__)

BLOB_PREFIX = "DICOM/"
LOOKUP_BATCH = 1000
SAMPLE_LIMIT = 20


@dataclass
class SweepResult:
    listed: int = 0
    reportable: int = 0
    new: int = 0
    pending: int = 0
    deletable: int = 0
    deleted: int = 0
    failed: int = 0
    bytes: int = 0
    breaker_tripped: bool = False
    earliest_deletion: datetime | None = None
    sample_keys: list[str] = field(default_factory=list)
    previous_run: datetime | None = None


def sweep_orphans(*, delete: bool, force: bool = False, notify: bool = True, record: bool = True,
                  now: datetime | None = None) -> SweepResult:
    """One sweep. `delete=False` reports only. `notify`/`record` gate the staff email and the audit event
    (the management command's dry run sets both False so it never moves the previous-run gate)."""
    now = now or timezone.now()
    detect = timedelta(hours=settings.DICOM_ORPHAN_DETECT_HOURS)
    grace = timedelta(hours=settings.DICOM_ORPHAN_GRACE_HOURS)
    result = SweepResult(previous_run=_previous_run())
    prev = result.previous_run
    deletable: list[str] = []

    for batch in _batches(DicomStorage().iter_blobs(BLOB_PREFIX)):
        result.listed += len(batch)
        known = set(DicomFile.objects.filter(file__in=[b[0] for b in batch]).values_list("file", flat=True))
        for name, size, modified in batch:
            if name in known or now - modified < detect:
                continue
            result.reportable += 1
            result.bytes += size
            if len(result.sample_keys) < SAMPLE_LIMIT:
                result.sample_keys.append(name)
            if prev is None or modified >= prev - detect:
                result.new += 1
            if now - modified >= grace and prev is not None and modified < prev - detect:
                deletable.append(name)
            else:
                result.pending += 1
                due = modified + grace
                if result.earliest_deletion is None or due < result.earliest_deletion:
                    result.earliest_deletion = due

    result.deletable = len(deletable)
    result.breaker_tripped = not force and (
        len(deletable) > settings.DICOM_ORPHAN_MAX_DELETE_COUNT
        or len(deletable) > settings.DICOM_ORPHAN_MAX_DELETE_FRACTION * result.listed)
    if delete and not result.breaker_tripped:
        _delete(deletable, result)

    logger.info(
        "DICOM orphan sweep: listed=%d reportable=%d new=%d pending=%d deletable=%d deleted=%d failed=%d "
        "bytes=%d breaker_tripped=%s", result.listed, result.reportable, result.new, result.pending,
        result.deletable, result.deleted, result.failed, result.bytes, result.breaker_tripped)
    if record:
        _record(result, now, deleting=delete)
    if notify and (result.reportable or result.failed):
        _email_staff(result, deleting=delete)
    return result


def _batches(blobs):
    batch = []
    for blob in blobs:
        batch.append(blob)
        if len(batch) >= LOOKUP_BATCH:
            yield batch
            batch = []
    if batch:
        yield batch


def _delete(names: list[str], result: SweepResult) -> None:
    storage = DicomStorage()
    for name in names:
        if DicomFile.objects.filter(file=name).exists():  # a row appeared since the listing
            continue
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 -- one failing delete must not stop the run
            logger.exception("DICOM orphan sweep: delete failed for %s", name)
            result.failed += 1
        else:
            result.deleted += 1


def _previous_run() -> datetime | None:
    last = AuditLog.objects.filter(event_type=EVENT_TYPE_DICOM_ORPHAN_SWEEP).order_by("-logtime").first()
    run_at = (last.metadata or {}).get("run_at") if last else None
    return datetime.fromisoformat(run_at) if run_at else None


def _record(result: SweepResult, now: datetime, *, deleting: bool) -> None:
    AuditLog.objects.record(EVENT_TYPE_DICOM_ORPHAN_SWEEP, metadata={
        "run_at": now.isoformat(), "mode": "delete" if deleting else "report",
        "listed": result.listed, "reportable": result.reportable, "new": result.new,
        "pending": result.pending, "deletable": result.deletable, "deleted": result.deleted,
        "failed": result.failed, "bytes": result.bytes, "breaker_tripped": result.breaker_tripped,
        "sample_keys": result.sample_keys,
    })


def _email_staff(result: SweepResult, *, deleting: bool) -> None:
    recipients = sorted(
        get_user_model().objects.filter(is_staff=True).exclude(email="").values_list("email", flat=True))
    if not recipients:
        return
    lines = [
        f"Orphan DICOM blobs (no database row): {result.reportable}, total {result.bytes} bytes.",
        f"New since the previous run: {result.new}.",
        f"Pending deletion: {result.pending}"
        + (f" (earliest deletion {result.earliest_deletion.isoformat()})." if result.earliest_deletion else "."),
        f"Deleted this run: {result.deleted}." if deleting else "Report-only run: nothing deleted.",
    ]
    if result.failed:
        lines.append(f"Failed deletes: {result.failed} (see the server log).")
    if result.breaker_tripped:
        lines.append(
            f"Circuit breaker tripped: {result.deletable} blobs were due for deletion, over the configured "
            "limit, so nothing was deleted. If the database was restored, check it; otherwise run "
            "`sweep_dicom_orphans --delete --force`.")
    lines.append(f"Sample keys (up to {SAMPLE_LIMIT}):")
    lines.extend(result.sample_keys)
    send_mail(
        subject="MiqaResearch: orphan DICOM blobs found", message="\n".join(lines),
        from_email=settings.NO_REPLY_EMAIL_ADDRESS, recipient_list=recipients)

"""ETL orchestrator (#162): running one queued EtlJob to completion.

Fetches each input's bytes (stamping the real SHA-256/size onto its EtlJobInput row -- the
poller only ever wrote placeholders, since hashing at poll time would mean fetching every object
twice), builds the sandbox contract's manifest (`{"datatype": ..., "config": ...}`) and
SandboxRunSpec from the Job's own pinned Script Version and config snapshot (#224: a Binding edit
never changes a Job already queued), and runs it through the configured
SandboxBackend. On exit 0 the result (header line dropped, per mires_etl.contract's manifest/result
shape) is handed to the real Datatype loader (#159) inside its own all-or-nothing transaction.
Every other exit code (1 script error / 2 contract violation / 3 timeout-or-killed) fails the Job
without a retry -- matching #156's spec text that groups all three as requiring manual retry.

A SandboxBackend.run() raising -- meaning no container was ever started -- is not this module's
concern beyond delegating to `retry.handle_run_exception`, shared with stuck-job recovery
(stuck.py), since both are "the run never produced a result" cases.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from contract.constants.etl import (
    ETL_JOB_STATUS_FAILED,
    ETL_JOB_STATUS_PENDING,
    ETL_JOB_STATUS_RUNNING,
    ETL_JOB_STATUS_SUCCEEDED,
)
from MiqaResearch.data.models import EtlJob
from MiqaResearch.etl_datatypes import EtlDatatypeError, load_jsonl
from MiqaResearch.etl_sandbox import (
    SandboxInputTooLarge,
    SandboxRunSpec,
    StagedInput,
    get_sandbox_backend,
    resolve_limits,
)
from MiqaResearch.etl_sandbox._staging import check_input_size
from mires_etl import contract

from . import retry
from .s3 import EtlBucketSource

LOG_CAP_BYTES = 64 * 1024


def run_job(job_id: str) -> EtlJob:
    job = EtlJob.objects.select_related("binding__project", "script_version__script").get(pk=job_id)
    if job.status != ETL_JOB_STATUS_PENDING:
        # Already running/finished -- a retried task dispatch, or a duplicate enqueue. No-op.
        return job

    job.status = ETL_JOB_STATUS_RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    scratch = _make_scratch_dir()
    try:
        return _run_in_scratch(job, scratch)
    finally:
        # The loader's `inputs` reader opens the staged files, so scratch lives until the Job is finalized.
        shutil.rmtree(scratch, ignore_errors=True)


def _run_in_scratch(job: EtlJob, scratch: Path) -> EtlJob:
    binding = job.binding
    source = EtlBucketSource(binding.source_bucket, binding.source_prefix, binding.storage)
    job_inputs = list(job.inputs.all())
    staged = []
    for job_input in job_inputs:
        relative = _relative_key(binding, job_input.key)
        staged.append(StagedInput(
            relative_path=relative, size=source.size_of(job_input.key),
            local_path=_input_path(scratch, relative)))

    script = job.script_version.script
    spec = SandboxRunSpec(
        run_id=str(job.id),
        image_key=job.script_version.image_key,
        manifest={"datatype": script.datatype_name, "config": job.config_snapshot},
        script_source=job.script_version.source.read(),
        limits=resolve_limits(binding),
        input_files=staged,
        scratch_dir=scratch,
    )

    try:
        check_input_size(spec)  # on listed sizes, before anything is fetched
    except SandboxInputTooLarge as exc:
        retry.handle_run_exception(job, exc)
        job.refresh_from_db()
        return job

    total = sum(staged_input.size for staged_input in staged)
    free = shutil.disk_usage(scratch).free
    needed = total + settings.ETL_SCRATCH_MARGIN_BYTES
    if free < needed:
        retry.retry_infra_failure(
            job, reason=f"insufficient scratch space in {scratch.parent}: {free} bytes free, "
                        f"{needed} needed ({total} input + margin)")
        job.refresh_from_db()
        return job

    for job_input, staged_input in zip(job_inputs, staged, strict=True):
        sha256, size = source.download(job_input.key, staged_input.local_path)
        if size != staged_input.size:
            retry.fail_job(
                job, reason=f"input {job_input.key!r} changed while being read: "
                            f"listed {staged_input.size} bytes, fetched {size}")
            job.refresh_from_db()
            return job
        job_input.sha256 = sha256
        job_input.size_bytes = size
        job_input.save(update_fields=["sha256", "size_bytes"])

    backend = get_sandbox_backend()
    try:
        result = backend.run(spec)
    except Exception as exc:  # noqa: BLE001 -- classified by retry.handle_run_exception
        retry.handle_run_exception(job, exc)
        job.refresh_from_db()
        return job

    return _finalize(job, result)


def _make_scratch_dir() -> Path:
    """A per-Job scratch dir (mode 0700 via mkdtemp) on the configured volume."""
    base = settings.ETL_SCRATCH_DIR or None
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="mires-etl-", dir=base))


def _input_path(scratch: Path, relative: str) -> Path:
    root = (scratch / "input").resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"input path escapes the scratch directory: {relative!r}")
    return path


def _finalize(job: EtlJob, result) -> EtlJob:
    job.finished_at = timezone.now()
    job.log = _cap_log(result.log)

    if result.exit_code == contract.EXIT_SUCCESS:
        try:
            _load_result(job, result.result_jsonl)
        except EtlDatatypeError as exc:
            job.status = ETL_JOB_STATUS_FAILED
            job.log = (job.log + f"\n[orchestrator] loader rejected the result: {exc}").strip()
        else:
            job.status = ETL_JOB_STATUS_SUCCEEDED
    else:
        # Exit 1 (script error), 2 (contract violation), 3 (timeout/killed): all script-class,
        # none auto-retry (#156's spec text groups them explicitly under "manual retry").
        job.status = ETL_JOB_STATUS_FAILED

    job.save(update_fields=["status", "finished_at", "log"])
    if job.status == ETL_JOB_STATUS_SUCCEEDED:
        # Only once "succeeded" is saved: the mover skips any other status, and under "delete"
        # Raw Retention a move for an unrecorded success would lose the source (#246).
        _enqueue_raw_bucket_move(job)
    return job


def _load_result(job: EtlJob, result_jsonl: bytes | None) -> None:
    if not result_jsonl:
        raise EtlDatatypeError("sandbox reported success (exit 0) but wrote no result.jsonl")
    text = result_jsonl.decode("utf-8")
    body = "\n".join(text.splitlines()[1:])  # drop the header line: {"datatype": "<name>"}
    load_jsonl(
        datatype_name=job.script_version.script.datatype_name,
        project=job.binding.project, etl_job=job, jsonl_text=body)


def _enqueue_raw_bucket_move(job: EtlJob) -> None:
    """#163: on success, the Job's inputs get moved to the raw bucket. Deferred import to avoid
    the same circular-import shape as retry.py's `.tasks` import (tasks.py -> runner.py)."""
    from .tasks import move_etl_job_inputs_to_raw_bucket
    move_etl_job_inputs_to_raw_bucket.enqueue(str(job.id))


def _relative_key(binding, key: str) -> str:
    prefix = binding.source_prefix
    relative = key[len(prefix):] if key.startswith(prefix) else key
    return relative.lstrip("/")


def _cap_log(log_bytes: bytes) -> str:
    text = log_bytes.decode("utf-8", errors="replace")
    encoded = text.encode("utf-8")
    if len(encoded) <= LOG_CAP_BYTES:
        return text
    # Keep the tail: a truncated script log is most useful right before it stopped.
    return encoded[-LOG_CAP_BYTES:].decode("utf-8", errors="ignore")

"""DICOM ingestion pipeline — top-level test seam (#98 testing decisions, #119, #120).

`run_ingestion` is plain and directly callable: it runs the staged pipeline
(discovery → parse → participant match/create → UID pseudonymization →
extraction → record upsert → storage → report) synchronously in one
invocation, mirroring the OCR pipeline's orchestrator structure
(tasks/ocr/pipeline.py). Tests call this function directly, bypassing task
dispatch; the django.tasks/Celery wrapper is a later ticket.

A run's source is exactly one of: a local file path, a local folder path
(scanned fully recursively), or an ``s3://bucket[/prefix]`` location. Source
for a run fails the run immediately (discovery.SourceError); per-file problems
are reported per file in the run's report.
"""
import hashlib
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from django.conf import settings as django_settings
from django.db import transaction

from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.data.models import DicomFile, ResearchProject

from . import discovery, dicom_parsing, extractors, frame_index, pixel_bounds, records
from . import participant as participant_stage
from . import storage as storage_stage
from .dicom_parsing import NotADicomError
from .pixel_bounds import ImplausiblePixelDimensionsError

logger = logging.getLogger(__name__)

OUTCOME_INGESTED = "ingested"
OUTCOME_SKIPPED_DUPLICATE = "skipped_duplicate"
OUTCOME_DUPLICATE_CONFLICT = "duplicate_conflict"
OUTCOME_ERROR = "error"

# (dataset keyword, pseudonym key) for the UIDs pseudonymized before anything
# reaches the database or retained metadata (#115).
_UID_PSEUDONYM_KEYS = (
    ("StudyInstanceUID", "study"),
    ("SeriesInstanceUID", "series"),
    ("SOPInstanceUID", "sop"),
)

_REQUIRED_PSEUDONYM_KEYS = ("study", "series", "sop")


@dataclass
class FileIngestionResult:
    """Per-file outcome for the run's report. Never carries raw PHI values —
    only the source path, the pseudonymized SOP Instance UID, and the
    participant's existing pseudonymous alias."""

    source_path: str
    outcome: str
    error: str | None = None
    sop_instance_uid: str | None = None
    study_participant_alias: str | None = None
    dcm_file_id: UUID | None = None
    # Set when this run wrote new bytes to storage and read them back to
    # confirm they match (#123). Gates source-retention deletion — never set
    # for a duplicate that wasn't written this run (skipped, or conflicting
    # without an update), since nothing was verified in that case.
    stored_and_verified: bool = False


@dataclass
class IngestionReport:
    """Structured summary of one ingestion run: counts plus the per-file list."""

    research_project_id: UUID
    results: list[FileIngestionResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            OUTCOME_INGESTED: sum(result.outcome == OUTCOME_INGESTED for result in self.results),
            OUTCOME_SKIPPED_DUPLICATE: sum(result.outcome == OUTCOME_SKIPPED_DUPLICATE for result in self.results),
            OUTCOME_DUPLICATE_CONFLICT: sum(result.outcome == OUTCOME_DUPLICATE_CONFLICT for result in self.results),
            OUTCOME_ERROR: sum(result.outcome == OUTCOME_ERROR for result in self.results),
        }


def run_ingestion(
    research_project: ResearchProject,
    source: str | Path,
    overwrite_existing: bool | None = None,
    delete_originals_after_storage: bool | None = None,
) -> IngestionReport:
    """Ingest every DICOM file under `source` into `research_project` and report the outcomes.

    `source` is exactly one of: a local file path, a local folder path (scanned
    fully recursively, DICOM detected by content regardless of extension), or an
    "s3://bucket[/prefix]" location. Source-level problems (missing or
    inaccessible source, a local source outside the configured allow-list, an
    unreachable S3 bucket) raise discovery.SourceError subclasses and fail the
    run immediately — distinct from a run that completes having found zero
    files. Per-file problems are recorded as error outcomes and never abort the
    run. `overwrite_existing` overrides the project's duplicate-handling
    setting (skip/update) for this run only; None keeps the project setting.

    `delete_originals_after_storage` governs source retention (#123): once a
    file's stored copy is read back and confirmed to match, its source is
    deleted. Most-specific-wins: this run-level override, else the project's
    `dicom_delete_originals_after_storage`, else the global
    `DICOM_DELETE_ORIGINALS_AFTER_STORAGE` setting. A file whose storage isn't
    verified this run (duplicate skip, or a conflict left unwritten) is never
    deleted, regardless of the setting.
    """
    delete_originals = _resolve_delete_originals_after_storage(research_project, delete_originals_after_storage)
    report = IngestionReport(research_project_id=research_project.id)
    if _is_s3_source(source):
        _run_s3_source(research_project, source, overwrite_existing, delete_originals, report)
        return report
    _run_local_source(research_project, source, overwrite_existing, delete_originals, report)
    return report


def _resolve_delete_originals_after_storage(research_project: ResearchProject, run_override: bool | None) -> bool:
    """Most-specific-wins: run override > project override > global default (#123)."""
    if run_override is not None:
        return run_override
    if research_project.dicom_delete_originals_after_storage is not None:
        return research_project.dicom_delete_originals_after_storage
    return django_settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE


def _is_s3_source(source) -> bool:
    return isinstance(source, str) and source.startswith("s3://")


def _run_local_source(
    research_project: ResearchProject,
    source: str | Path,
    overwrite_existing: bool | None,
    delete_originals: bool,
    report: IngestionReport,
) -> None:
    allowed_roots = django_settings.DICOM_ALLOWED_SOURCE_ROOTS
    # discover_local_files validates the top-level source (allow-list,
    # existence, accessibility) and fails the run immediately on any problem.
    for file_path in discovery.discover_local_files(source, allowed_roots):
        # Per-file gate: a symlink found mid-walk may resolve outside the
        # allow-list even though the top-level source passed — reject before read.
        try:
            discovery.assert_local_source_allowed(file_path, allowed_roots)
        except discovery.SourceNotAllowedError:
            report.results.append(
                FileIngestionResult(source_path=str(file_path), outcome=OUTCOME_ERROR, error="file resolves outside the allowed source roots")
            )
            continue
        try:
            raw_bytes = file_path.read_bytes()
        except OSError as exc:
            report.results.append(
                FileIngestionResult(source_path=str(file_path), outcome=OUTCOME_ERROR, error=f"source file unreadable: {type(exc).__name__}")
            )
            continue
        result = _ingest_file(research_project, str(file_path), raw_bytes, overwrite_existing)
        report.results.append(result)
        if delete_originals and result.stored_and_verified:
            _delete_local_source(file_path)


def _delete_local_source(file_path: Path) -> None:
    """Delete exactly the source file this run just read and verified (#123)."""
    try:
        file_path.unlink()
    except OSError:
        logger.exception("Could not delete verified source file %s after storage", file_path)


def _run_s3_source(
    research_project: ResearchProject,
    source: str,
    overwrite_existing: bool | None,
    delete_originals: bool,
    report: IngestionReport,
) -> None:
    # Opening/validating the source fails the run immediately (S3SourceError).
    s3_source = discovery.S3Source(source)
    for ref in s3_source.list_objects():
        try:
            raw_bytes = s3_source.read(ref)
        except discovery.S3SourceError:
            # The source was reachable at discovery time but this object can't
            # be read now — a per-file problem, not a source-level failure.
            report.results.append(
                FileIngestionResult(source_path=ref.uri, outcome=OUTCOME_ERROR, error="S3 object unreadable")
            )
            continue
        result = _ingest_file(research_project, ref.uri, raw_bytes, overwrite_existing)
        report.results.append(result)
        if delete_originals and result.stored_and_verified:
            _delete_s3_source(s3_source, ref)


def _delete_s3_source(s3_source: discovery.S3Source, ref: discovery.S3ObjectRef) -> None:
    """Delete exactly the source object this run just read and verified (#123)."""
    try:
        s3_source.delete(ref)
    except discovery.S3SourceError:
        logger.exception("Could not delete verified source object %s after storage", ref.uri)


def _ingest_file(
    research_project: ResearchProject,
    source_path: str,
    raw_bytes: bytes,
    overwrite_existing: bool | None,
) -> FileIngestionResult:
    """The single-file pipeline core: parse → pseudonymize → upsert → store.

    Returns the file's FileIngestionResult; the run collects one per file.
    """

    def finish(outcome: str, **kwargs) -> FileIngestionResult:
        return FileIngestionResult(source_path=source_path, outcome=outcome, **kwargs)

    try:
        dataset = dicom_parsing.parse_dicom(raw_bytes)
    except NotADicomError:
        return finish(OUTCOME_ERROR, error="not a DICOM file")
    except Exception:
        return finish(OUTCOME_ERROR, error="DICOM parse error")

    try:
        pixel_bounds.assert_plausible_pixel_dimensions(
            dataset, django_settings.DICOM_MAX_PIXEL_DIMENSIONS, django_settings.DICOM_MAX_FRAME_COUNT
        )
    except ImplausiblePixelDimensionsError as exc:
        return finish(OUTCOME_ERROR, error=str(exc))

    try:
        pseudonyms = _pseudonymize_uids(dataset, research_project)
    except Exception:
        return finish(OUTCOME_ERROR, error="UID pseudonymization failed")
    if pseudonyms is None:
        return finish(OUTCOME_ERROR, error="missing required UID tag (StudyInstanceUID or SeriesInstanceUID)")

    sop_pseudonym = pseudonyms["sop"]
    try:
        with transaction.atomic():
            existing = (
                DicomFile.objects.select_related("series__study__study_participant")
                .filter(sop_instance_uid=sop_pseudonym)
                .first()
            )
            if existing is not None:
                outcome, stored_and_verified = _handle_duplicate(
                    existing, dataset, research_project, raw_bytes, overwrite_existing
                )
                return finish(outcome, sop_instance_uid=sop_pseudonym, stored_and_verified=stored_and_verified)
            participant = participant_stage.match_or_create_participant(dataset, research_project)
            extracted = extractors.extract(dataset, research_project, participant.alias1)
            file_size_in_mb = len(raw_bytes) / (1024 * 1024)
            dcm_file = records.build_hierarchy(
                participant, research_project, pseudonyms, extracted, file_size_in_mb
            )
            dcm_file.content_sha256 = _content_hash(raw_bytes)
            _set_frame_index(dcm_file, raw_bytes)
            storage_stage.store_file_bytes(dcm_file, raw_bytes)
            dcm_file.save()
            records.add_file_size_to_series(dcm_file.series, file_size_in_mb)
            stored_and_verified = _verify_stored(dcm_file, dcm_file.content_sha256, source_path)
    except ValueError:
        # match_or_create_participant: the file has no usable patient identifier
        return finish(OUTCOME_ERROR, error="no usable patient identifier (PatientID missing or empty)")
    except Exception:
        logger.exception("DICOM ingestion failed for %s", source_path)
        return finish(OUTCOME_ERROR, error="ingestion failed", sop_instance_uid=sop_pseudonym)

    return finish(
        OUTCOME_INGESTED,
        sop_instance_uid=sop_pseudonym,
        study_participant_alias=participant.alias1,
        dcm_file_id=dcm_file.id,
        stored_and_verified=stored_and_verified,
    )


def _verify_stored(dcm_file: DicomFile, expected_sha256: str, source_path: str) -> bool:
    """Read back what was just stored and confirm it matches (#123).

    A verification failure never fails the ingestion itself — the record is
    already valid and saved — it only withholds the go-ahead for source
    retention to delete the original.
    """
    try:
        return storage_stage.verify_stored_bytes(dcm_file, expected_sha256)
    except Exception:
        logger.exception("Stored-file verification failed for %s", source_path)
        return False


def _handle_duplicate(
    existing: DicomFile,
    dataset,
    research_project: ResearchProject,
    raw_bytes: bytes,
    overwrite_existing: bool | None,
) -> tuple[str, bool]:
    """Resolve a file whose pseudonymized SOP UID is already stored (#120).

    Identical content is a no-op duplicate in either mode. Differing content is
    always reported as a conflict; only in update mode is the record replaced
    in place (file-level data; Study/Series fields stay fill-blank-only).
    Must run inside the caller's transaction.

    Returns (outcome, stored_and_verified) — the second only True when this
    call itself wrote new bytes and read them back to confirm they match
    (#123); a skipped or unwritten conflict never verifies anything this run.
    """
    new_hash = _content_hash(raw_bytes)
    if new_hash == _stored_content_hash(existing):
        return OUTCOME_SKIPPED_DUPLICATE, False
    update = overwrite_existing if overwrite_existing is not None else research_project.dicom_duplicate_handling == "update"
    if update:
        participant_alias = existing.series.study.study_participant.alias1
        extracted = extractors.extract(dataset, research_project, participant_alias)
        file_size_in_mb = len(raw_bytes) / (1024 * 1024)
        superseded = storage_stage.replace_file_bytes(existing, raw_bytes)
        _set_frame_index(existing, raw_bytes)
        records.update_file_in_place(existing, extracted, file_size_in_mb, new_hash)
        records.fill_study_series_blanks(existing.series, extracted)
        transaction.on_commit(lambda: storage_stage.discard_file(existing, superseded))
        stored_and_verified = _verify_stored(existing, new_hash, existing.file.name)
        return OUTCOME_DUPLICATE_CONFLICT, stored_and_verified
    return OUTCOME_DUPLICATE_CONFLICT, False


def _set_frame_index(dcm_file: DicomFile, raw_bytes: bytes) -> None:
    """Record the stored file's transfer syntax and frame offset index (#274) for WADO-RS /frames."""
    try:
        index = frame_index.build_frame_index(io.BytesIO(raw_bytes))
    except Exception:
        # Never fail ingestion over the index: a null index is rebuilt on first /frames request or by the backfill.
        logger.exception("Could not build the frame offset index for %s", dcm_file.sop_instance_uid)
        return
    dcm_file.transfer_syntax_uid = index.transfer_syntax_uid or None
    dcm_file.frame_index = index.frames


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stored_content_hash(dcm_file: DicomFile) -> str:
    """SHA-256 of the stored bytes; legacy rows without a stored hash are hashed from the file."""
    if dcm_file.content_sha256:
        return dcm_file.content_sha256
    with dcm_file.file.storage.open(dcm_file.file.name, "rb") as stored:
        return _content_hash(stored.read())


def _pseudonymize_uids(dataset, research_project: ResearchProject) -> dict[str, str] | None:
    """Pseudonymize the file's UIDs for the project, or None when a required one is absent."""
    pseudonyms: dict[str, str] = {}
    for keyword, key in _UID_PSEUDONYM_KEYS:
        value = str(dataset.get(keyword) or "").strip()
        if not value:
            if key in _REQUIRED_PSEUDONYM_KEYS:
                return None
            continue
        pseudonyms[key] = pseudonymize_uid(value, research_project)
    return pseudonyms

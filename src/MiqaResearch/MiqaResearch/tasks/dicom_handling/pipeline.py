"""DICOM ingestion pipeline — top-level test seam (#98 testing decisions, #119).

`run_ingestion` is plain and directly callable: it runs the staged pipeline
(parse → participant match/create → UID pseudonymization → extraction →
record upsert → storage → report) synchronously in one invocation, mirroring
the OCR pipeline's orchestrator structure (tasks/ocr/pipeline.py). Tests call
this function directly, bypassing task dispatch; the django.tasks/Celery
wrapper is a later ticket.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from django.db import transaction

from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.data.models import DicomFile, ResearchProject

from . import dicom_parsing, extractors, records
from . import participant as participant_stage
from . import storage as storage_stage
from .dicom_parsing import NotADicomError

logger = logging.getLogger(__name__)

OUTCOME_INGESTED = "ingested"
OUTCOME_SKIPPED_DUPLICATE = "skipped_duplicate"
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
            OUTCOME_ERROR: sum(result.outcome == OUTCOME_ERROR for result in self.results),
        }


def run_ingestion(research_project: ResearchProject, file_path: str | Path) -> IngestionReport:
    """Ingest one local DICOM file into `research_project` and report the outcome."""
    report = IngestionReport(research_project_id=research_project.id)
    path = Path(file_path)
    source_path = str(path)

    def finish(outcome: str, **kwargs) -> IngestionReport:
        report.results.append(FileIngestionResult(source_path=source_path, outcome=outcome, **kwargs))
        return report

    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return finish(OUTCOME_ERROR, error=f"source file unreadable: {type(exc).__name__}")

    try:
        dataset = dicom_parsing.parse_dicom(raw_bytes)
    except NotADicomError:
        return finish(OUTCOME_ERROR, error="not a DICOM file")
    except Exception:
        return finish(OUTCOME_ERROR, error="DICOM parse error")

    try:
        pseudonyms = _pseudonymize_uids(dataset, research_project)
    except Exception:
        return finish(OUTCOME_ERROR, error="UID pseudonymization failed")
    if pseudonyms is None:
        return finish(OUTCOME_ERROR, error="missing required UID tag (StudyInstanceUID or SeriesInstanceUID)")

    sop_pseudonym = pseudonyms["sop"]
    try:
        with transaction.atomic():
            if DicomFile.objects.filter(sop_instance_uid=sop_pseudonym).exists():
                return finish(OUTCOME_SKIPPED_DUPLICATE, sop_instance_uid=sop_pseudonym)
            participant = participant_stage.match_or_create_participant(dataset, research_project)
            extracted = extractors.extract(dataset, research_project)
            file_size_in_mb = len(raw_bytes) / (1024 * 1024)
            dcm_file = records.build_hierarchy(
                participant, research_project, pseudonyms, extracted, file_size_in_mb
            )
            storage_stage.store_file_bytes(dcm_file, raw_bytes)
            dcm_file.save()
            records.add_file_size_to_series(dcm_file.series, file_size_in_mb)
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
    )


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

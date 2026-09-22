"""Celery task wrapper around the DICOM ingestion pipeline (#103, #126).

Per #116's Testing Decisions, only the concurrency-focused performance test
(tests/test_dicom_ingestion_performance.py) dispatches this as a real task
onto the actual queue; every other ingestion test calls
`pipeline.run_ingestion` directly. A thin wrapper: id-resolution in, the
run's report out, serialized to plain JSON-safe types for the Celery result
backend -- per #103's resolution, the result carries per-file counts *and*
reasons, matching the OCR PipelineResult precedent, not just the counts.

An unknown `research_project_id` raises `ResearchProject.DoesNotExist`
rather than being caught and logged (unlike the OCR/consent task
precedents): there is no sensible partial result for a run that was never
scoped to a real project, so the task is marked FAILED and the caller sees
the DoesNotExist via the task result's errors, rather than a silent no-op.
"""
from django.tasks import task

from contract.constants.celery import QUEUE_DICOM_INGESTION
from MiqaResearch.data.models import ResearchProject

from .pipeline import FileIngestionResult, IngestionReport, run_ingestion


@task(queue_name=QUEUE_DICOM_INGESTION)
def ingest_dicom_source(research_project_id: str, source: str) -> dict:
    research_project = ResearchProject.objects.get(pk=research_project_id)
    report = run_ingestion(research_project, source)
    return _serialize_report(report)


def _serialize_report(report: IngestionReport) -> dict:
    return {
        "counts": report.counts,
        "results": [_serialize_result(result) for result in report.results],
    }


def _serialize_result(result: FileIngestionResult) -> dict:
    return {
        "source_path": result.source_path,
        "outcome": result.outcome,
        "error": result.error,
        "sop_instance_uid": result.sop_instance_uid,
        "study_participant_alias": result.study_participant_alias,
        "dcm_file_id": str(result.dcm_file_id) if result.dcm_file_id is not None else None,
        "stored_and_verified": result.stored_and_verified,
    }

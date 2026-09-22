"""Celery task wrapper around the DICOM ingestion pipeline (#103, #126).

Per #116's Testing Decisions, only the concurrency-focused performance test
(tests/test_dicom_ingestion_performance.py) dispatches this as a real task
onto the actual queue; every other ingestion test calls
`pipeline.run_ingestion` directly. A thin wrapper: id-resolution in, the
run's summary counts out -- the full per-file report never needs to survive
a Celery result round-trip.
"""
from django.tasks import task

from contract.constants.celery import QUEUE_DICOM_INGESTION
from MiqaResearch.data.models import ResearchProject

from .pipeline import run_ingestion


@task(queue_name=QUEUE_DICOM_INGESTION)
def ingest_dicom_source(research_project_id: str, source: str) -> dict[str, int]:
    research_project = ResearchProject.objects.get(pk=research_project_id)
    report = run_ingestion(research_project, source)
    return report.counts

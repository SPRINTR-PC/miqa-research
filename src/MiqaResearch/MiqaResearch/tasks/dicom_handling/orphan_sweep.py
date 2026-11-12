"""Daily 03:00 beat task for the orphan DICOM blob sweep (#420); logic in actions/dicom_ingest/orphan_sweep.py."""
from django.conf import settings
from django.tasks import task

from contract.constants.celery import QUEUE_DICOM_INGESTION
from MiqaResearch.actions.dicom_ingest.orphan_sweep import sweep_orphans


@task(queue_name=QUEUE_DICOM_INGESTION)
def sweep_dicom_orphans() -> dict:
    result = sweep_orphans(delete=settings.DICOM_ORPHAN_SWEEP_ACTION == "delete")
    return {
        "listed": result.listed, "reportable": result.reportable, "deleted": result.deleted,
        "failed": result.failed, "breaker_tripped": result.breaker_tripped,
    }

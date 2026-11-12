"""Backfill the frame offset index (#274) for DicomFiles ingested before it existed.

Idempotent: only rows whose index is still null are read, so a rerun (or a run
racing the lazy index-on-first-request in WADO-RS /frames) does no extra work.
Each row is indexed from its stored bytes and saved on its own, so one
unreadable file never blocks the rest; it stays null and is counted as failed.
"""
import logging

from django.tasks import task

from contract.constants.celery import QUEUE_DICOM_INGESTION
from MiqaResearch.data.models import DicomFile

from MiqaResearch.actions.dicom_ingest.frame_index import build_frame_index

logger = logging.getLogger(__name__)


@task(queue_name=QUEUE_DICOM_INGESTION)
def backfill_frame_indexes() -> dict:
    indexed = failed = 0
    for dicom_file in DicomFile.objects.filter(frame_index__isnull=True).only("id", "file").iterator(chunk_size=200):
        try:
            with dicom_file.file.open("rb") as stored:
                index = build_frame_index(stored)
        except Exception:
            logger.exception("Could not build the frame offset index for DicomFile %s", dicom_file.pk)
            failed += 1
            continue
        DicomFile.objects.filter(pk=dicom_file.pk, frame_index__isnull=True).update(
            transfer_syntax_uid=index.transfer_syntax_uid or None, frame_index=index.frames
        )
        indexed += 1
    return {"indexed": indexed, "failed": failed}

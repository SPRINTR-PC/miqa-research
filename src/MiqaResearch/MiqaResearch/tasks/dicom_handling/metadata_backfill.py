"""Backfill: re-sanitize existing `DicomFile.metadata` under the De-identification Profile (#273).

Dumps written before ADR 0028 only had 19 PHI tags stripped. This re-reads
each stored file's header, rebuilds the dump through the same path the
`dicom_instance` loader uses (so payload summaries such as `pathology_summary`
are rebuilt too) and writes it back only when it differs. Re-running is a no-op.
A file that can't be read is logged and counted; the run carries on.

Enqueue with `resanitize_dicom_metadata.enqueue()`, or run inline with
`resanitize_dicom_metadata.call()`.
"""
import logging

from django.tasks import task
from pydantic import TypeAdapter

from contract.constants.celery import QUEUE_DICOM_INGESTION
from MiqaResearch.actions.dicom_ingest.metadata_dump import build_metadata_dump, payload_metadata
from MiqaResearch.data.models import DicomFile
from MiqaResearch.etl_native_scripts import dicom_instance as native_script
from MiqaResearch.readers.participant_keys import participant_alias_of
from mires_etl.schemas.dicom_instance import Payload

from . import dicom_parsing

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 200
_PAYLOAD = TypeAdapter(Payload)


@task(queue_name=QUEUE_DICOM_INGESTION)
def resanitize_dicom_metadata() -> dict:
    counts = {"updated": 0, "unchanged": 0, "errors": 0}
    files = (
        DicomFile.objects.select_related(
            "research_project",
            "series__study__participant_key__study_participant",
            "series__study__participant_key__project",
        )
        .exclude(file="")
        # viewer-saved objects (#287) were stored already de-identified with pseudonymized UIDs
        .exclude(uids_pseudonymized=True)
        .order_by("pk")
    )
    for dcm_file in files.iterator(chunk_size=_CHUNK_SIZE):
        try:
            metadata = _rebuild_metadata(dcm_file)
        except Exception:
            logger.exception("Could not re-sanitize metadata for DicomFile %s", dcm_file.pk)
            counts["errors"] += 1
            continue
        if metadata == dcm_file.metadata:
            counts["unchanged"] += 1
            continue
        DicomFile.objects.filter(pk=dcm_file.pk).update(metadata=metadata)
        counts["updated"] += 1
    return counts


def _rebuild_metadata(dcm_file: DicomFile) -> dict:
    key = dcm_file.series.study.participant_key
    research_project = dcm_file.research_project or key.project
    with dcm_file.file.storage.open(dcm_file.file.name, "rb") as stored:
        dataset = dicom_parsing.parse_dicom(stored.read())
    # the native script's header summary (private helpers: the script stays a self-contained file)
    payload, _ = native_script._payload_and_geometry(dataset, native_script._sop_class_uid(dataset))
    metadata = build_metadata_dump(dataset, research_project, participant_alias_of(key))
    metadata.update(payload_metadata(_PAYLOAD.validate_python(payload), research_project))
    return metadata

"""Save, Supersede and Retire viewer-made Annotations and Segmentations (ADR 0026, #287).

The browser builds the SR/SEG; nothing in it is trusted. The server
de-identifies it with the shared sanitizer, then writes the patient, study,
series and instance identity from the database, and stores it as an ordinary
Dicom Series in the source Dicom Study. The stored bytes already carry
pseudonymized UIDs (`DicomFile.uids_pseudonymized`), because the references the
viewer got from WADO /metadata are pseudonyms; they are never hashed again.
"""
import hashlib
import io
import logging
from dataclasses import dataclass
from uuid import UUID, uuid7

import pydicom
from django.db import IntegrityError, transaction
from django.utils import timezone
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

from contract.constants.annotation import (
    KIND_ANNOTATION,
    KIND_BY_MODALITY,
    KIND_SEGMENTATION,
    SOURCE_VIEWER,
    VIEWER_SAVE_MODALITIES,
)
from contract.constants.audit_log import (
    EVENT_TYPE_ANNOTATION_CREATED,
    EVENT_TYPE_ANNOTATION_RETIRED,
    EVENT_TYPE_ANNOTATION_SUPERSEDED,
    EVENT_TYPE_SEGMENTATION_CREATED,
    EVENT_TYPE_SEGMENTATION_RETIRED,
    EVENT_TYPE_SEGMENTATION_SUPERSEDED,
)
from helpers.dicom_deidentification import deidentify
from MiqaResearch.actions.viewer_exceptions import NotAllowed, NotFound, ViewerActionError
from MiqaResearch.data.models import AuditLog, DerivedObjectProvenance, DicomFile, DicomSeries
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.blinding import ParticipantBlinding, viewer_reveals
from MiqaResearch.readers.participant_visibility import can_open_unlinked, can_see_participant
from MiqaResearch.tasks.dicom_handling import frame_index, records
from MiqaResearch.tasks.dicom_handling import storage as storage_stage
from MiqaResearch.tasks.dicom_handling.metadata_dump import build_metadata_dump

logger = logging.getLogger(__name__)

# kind -> (create, supersede, retire) audit event types
_EVENTS = {
    KIND_ANNOTATION: (EVENT_TYPE_ANNOTATION_CREATED, EVENT_TYPE_ANNOTATION_SUPERSEDED, EVENT_TYPE_ANNOTATION_RETIRED),
    KIND_SEGMENTATION: (
        EVENT_TYPE_SEGMENTATION_CREATED, EVENT_TYPE_SEGMENTATION_SUPERSEDED, EVENT_TYPE_SEGMENTATION_RETIRED,
    ),
}


class InvalidObject(ViewerActionError):
    """The upload or its source series can't be saved as asked."""


@dataclass
class StaleHead(ViewerActionError):
    """The version the caller edited is no longer the chain's head (or the chain is retired).

    `can_change`: whether the caller may supersede or retire that head (the viewer's "Save mine on top", #289).
    """

    head: DerivedObjectProvenance
    can_change: bool = False


def save_viewer_object(
    *,
    user,
    raw_bytes: bytes,
    source_series_uids: list[str],
    supersedes: UUID | None = None,
    request=None,
) -> DerivedObjectProvenance:
    """Store a browser-built SR or SEG as a new Annotation/Segmentation, or as the next version of one.

    `source_series_uids` are the (pseudonymized) Series Instance UIDs it was made on; the first is the
    base series, whose Dicom Study receives the new series. `supersedes` is the head the user edited.
    """
    if not source_series_uids:
        raise InvalidObject("at least one source series is required")
    dataset = _parse(raw_bytes)
    modality = str(dataset.get("Modality") or "").strip()
    if modality not in VIEWER_SAVE_MODALITIES:
        raise InvalidObject("only SR and SEG objects can be saved from the viewer")
    kind = KIND_BY_MODALITY[modality]

    with transaction.atomic():
        sources = _source_series(source_series_uids)
        study = sources[0].study
        participant = study.participant_key.study_participant
        project = study.participant_key.project
        if participant is None:
            # unlinked Study (ADR 0035): hidden from who may not open it, else refused until linked
            raise NotAllowed("link the Study to a participant before saving Annotations or Segmentations") \
                if can_open_unlinked(user, project) else NotFound()
        if not can_see_participant(user, project, participant):
            raise NotFound()
        rights = ParticipantRights(user, project, participant)
        if not rights.can_author:
            raise NotAllowed("your roles don't allow saving Annotations or Segmentations for this participant")
        frame_of_reference_uid = _shared_frame_of_reference(sources)
        blinding = ParticipantBlinding(user, project, participant, viewer_reveals(request))
        predecessor = _lock_head_to_supersede(supersedes, participant, kind, rights, blinding) if supersedes else None

        sanitized = deidentify(
            dataset, research_project=project, participant_alias=participant.alias1, uids_already_pseudonymized=True
        )
        _write_identity_from_db(sanitized, study, frame_of_reference_uid)
        stored_bytes = _serialize(sanitized)
        dcm_file = _store(sanitized, stored_bytes, study, project, participant.alias1, frame_of_reference_uid)
        try:
            with transaction.atomic():
                provenance = DerivedObjectProvenance.objects.create(
                    series=dcm_file.series,
                    kind=kind,
                    source=SOURCE_VIEWER,
                    author=user,
                    predecessor=predecessor,
                    version=predecessor.version + 1 if predecessor else 1,
                    base_series=sources[0],
                )
        except IntegrityError:
            _discard(dcm_file)
            if predecessor is None:
                raise
            # Another save took this head between our lock and insert (backstop for the lock)
            raise _stale(predecessor.chain_id, blinding, rights) from None
        provenance.source_series.set(sources)

        created_event, superseded_event, _ = _EVENTS[kind]
        AuditLog.objects.record(
            superseded_event if predecessor else created_event,
            user=user,
            request=request,
            project=project,
            metadata=_audit_metadata(provenance, participant, predecessor),
        )
    return provenance


def retire_object(*, user, object_id: UUID, request=None) -> DerivedObjectProvenance:
    """Retire a chain through its head. Retiring an already retired head is a no-op."""
    with transaction.atomic():
        provenance = (
            DerivedObjectProvenance.objects.select_for_update(of=("self",))
            .select_related(
                "series__study__participant_key__study_participant", "series__study__participant_key__project"
            )
            .filter(pk=object_id)
            .first()
        )
        if provenance is None:
            raise NotFound()
        participant = provenance.series.study.participant_key.study_participant
        project = provenance.series.study.participant_key.project
        if participant is None or not can_see_participant(user, project, participant):
            raise NotFound()
        blinding = ParticipantBlinding(user, project, participant, viewer_reveals(request))
        if blinding.hides(provenance.author_id):
            raise NotFound()
        if _has_successor(provenance):
            raise _stale(provenance.chain_id, blinding, ParticipantRights(user, project, participant))
        if provenance.retired:
            return provenance
        if not ParticipantRights(user, project, participant).can_change(provenance.author_id):
            raise NotAllowed("only the author, a PI, a Site PI or an Admin may retire this")
        provenance.retired = True
        provenance.retired_at = timezone.now()
        provenance.retired_by = user
        provenance.save(update_fields=["retired", "retired_at", "retired_by"])
        AuditLog.objects.record(
            _EVENTS[provenance.kind][2],
            user=user,
            request=request,
            project=project,
            metadata=_audit_metadata(provenance, participant, None),
        )
    return provenance


def _parse(raw_bytes: bytes) -> Dataset:
    try:
        dataset = pydicom.dcmread(io.BytesIO(raw_bytes))
    except Exception:
        raise InvalidObject("not a readable DICOM file") from None
    if not getattr(dataset, "file_meta", None) or "TransferSyntaxUID" not in dataset.file_meta:
        raise InvalidObject("the file has no Transfer Syntax UID")
    return dataset


def _source_series(uids: list[str]) -> list[DicomSeries]:
    found = {
        series.series_instance_uid: series
        for series in DicomSeries.objects.select_related(
            "study__participant_key__study_participant", "study__participant_key__project"
        ).filter(
            series_instance_uid__in=uids
        )
    }
    if len(found) != len(set(uids)):
        raise NotFound()
    ordered = list(dict.fromkeys(uids))
    sources = [found[uid] for uid in ordered]
    if len({_owner_of(series) for series in sources}) > 1:
        raise InvalidObject("all source series must belong to the same participant")
    return sources


def _owner_of(series: DicomSeries):
    """The participant the series belongs to, or its (unlinked) Participant Key."""
    key = series.study.participant_key
    return key.study_participant_id or key.pk


def _shared_frame_of_reference(sources: list[DicomSeries]) -> str | None:
    uids = set(
        DicomFile.objects.filter(series__in=sources)
        .exclude(frame_of_reference_uid__isnull=True)
        .exclude(frame_of_reference_uid="")
        .values_list("frame_of_reference_uid", flat=True)
        .distinct()
    )
    if len(uids) > 1:
        raise InvalidObject("source series must share one Frame of Reference")
    return next(iter(uids), None)


def _lock_head_to_supersede(
    object_id: UUID, participant, kind: str, rights: ParticipantRights, blinding: ParticipantBlinding
):
    predecessor = (
        DerivedObjectProvenance.objects.select_for_update(of=("self",))
        .select_related("series__study__participant_key")
        .filter(pk=object_id)
        .first()
    )
    if (
        predecessor is None
        or predecessor.series.study.participant_key.study_participant_id != participant.pk
        or blinding.hides(predecessor.author_id)
    ):
        raise NotFound()
    if predecessor.kind != kind:
        raise InvalidObject(f"a {kind} can't supersede a {predecessor.kind}")
    if predecessor.retired or _has_successor(predecessor):
        raise _stale(predecessor.chain_id, blinding, rights)
    if not rights.can_change(predecessor.author_id):
        raise NotAllowed("only the author, a PI, a Site PI or an Admin may supersede this")
    return predecessor


def _stale(chain_id, blinding: ParticipantBlinding, rights: ParticipantRights) -> ViewerActionError:
    """409 with the current head, or 404 when Blinded Annotation hides that head from the caller."""
    head = _head_of(chain_id)
    return NotFound() if blinding.hides(head.author_id) else StaleHead(head, rights.can_change(head.author_id))


def _has_successor(provenance: DerivedObjectProvenance) -> bool:
    return DerivedObjectProvenance.objects.filter(predecessor=provenance).exists()


def _head_of(chain_id) -> DerivedObjectProvenance:
    return (
        DerivedObjectProvenance.objects.select_related("series", "author")
        .filter(chain_id=chain_id, successor__isnull=True)
        .get()
    )


def _write_identity_from_db(ds: Dataset, study, frame_of_reference_uid: str | None) -> None:
    """Patient identity comes from the sanitizer; study, series and instance identity from here."""
    ds.StudyInstanceUID = study.study_instance_uid
    ds.StudyDate = study.study_datetime.strftime("%Y%m%d")
    ds.StudyTime = study.study_datetime.strftime("%H%M%S")
    if study.study_description:
        ds.StudyDescription = study.study_description
    elif "StudyDescription" in ds:
        del ds.StudyDescription
    ds.SeriesInstanceUID = generate_uid(prefix=None)
    ds.SOPInstanceUID = generate_uid(prefix=None)
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    if frame_of_reference_uid:
        ds.FrameOfReferenceUID = frame_of_reference_uid
    elif "FrameOfReferenceUID" in ds:
        del ds.FrameOfReferenceUID


def _serialize(ds: Dataset) -> bytes:
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def _store(
    ds: Dataset, stored_bytes: bytes, study, project, participant_alias: str, frame_of_reference_uid
) -> DicomFile:
    description = str(ds.get("SeriesDescription") or "").strip()[:128] or None
    series = DicomSeries.objects.create(
        study=study,
        series_instance_uid=ds.SeriesInstanceUID,
        modality=str(ds.Modality).strip(),
        series_description=description,
        frame_of_reference_uid=frame_of_reference_uid,
    )
    file_size_in_mb = len(stored_bytes) / (1024 * 1024)
    dcm_file = DicomFile(
        id=uuid7(),
        series=series,
        research_project=project,
        sop_instance_uid=ds.SOPInstanceUID,
        metadata=build_metadata_dump(ds, project, participant_alias, uids_already_pseudonymized=True),
        file_size_in_mb=file_size_in_mb,
        frame_of_reference_uid=frame_of_reference_uid,
        content_sha256=hashlib.sha256(stored_bytes).hexdigest(),
        uids_pseudonymized=True,
    )
    try:
        index = frame_index.build_frame_index(io.BytesIO(stored_bytes))
        dcm_file.transfer_syntax_uid = index.transfer_syntax_uid or None
        dcm_file.frame_index = index.frames
    except Exception:
        # Never fail a save over the index: a null one is rebuilt on first /frames request or by the backfill
        logger.exception("Could not build the frame offset index for %s", dcm_file.sop_instance_uid)
    storage_stage.store_file_bytes(dcm_file, stored_bytes)
    dcm_file.save()
    records.add_file_size_to_series(series, file_size_in_mb)
    return dcm_file


def _discard(dcm_file: DicomFile) -> None:
    """Delete bytes stored by a save that is being rolled back."""
    try:
        dcm_file.file.storage.delete(dcm_file.file.name)
    except Exception:
        logger.exception("Could not delete the stored bytes of rolled-back save %s", dcm_file.sop_instance_uid)


def _audit_metadata(provenance, participant, predecessor) -> dict:
    metadata = {
        "object_id": str(provenance.pk),
        "chain_id": str(provenance.chain_id),
        "version": provenance.version,
        "series_instance_uid": provenance.series.series_instance_uid,
        "participant_id": str(participant.pk),
    }
    if predecessor is not None:
        metadata["predecessor_series_instance_uid"] = predecessor.series.series_instance_uid
    return metadata

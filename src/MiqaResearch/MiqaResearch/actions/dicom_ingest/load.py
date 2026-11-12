"""Load validated `dicom_instance` rows into Studies, Series and Files (#418, spec #411, ADR 0036).

The sandboxed script only parses headers; this is where every write happens. Per Job, inside the
caller's single transaction:

1. Script-skipped rows keep their input in the source.
2. Per Study, the identifiers observed on its rows resolve to one Participant Key (ADR 0035).
3. Per file: read the staged original (sha256 must equal the runner-stamped `EtlJobInput.sha256`),
   re-parse it (the row's UIDs must match the bytes; implausible pixel dimensions fail), pseudonymize
   every UID incl. payload references, rebuild the sanitized metadata from the bytes (the script's `tags`
   dump is never read), store the blob, build the frame index, write the records and read the blob back.

Blobs written are deleted if anything fails; blobs replaced in update mode are discarded `on_commit`.
Failures raise `EtlLoadError` (no PHI in messages).
"""
import hashlib
import io
import logging
from collections import Counter
from datetime import UTC

import pydicom
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contract.constants.participant_key import DICOM_KEY_TAG_ALLOWLIST
from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.actions.participant_keys import ParticipantKeyError, link_study_keys
from MiqaResearch.data.models import DerivedObjectProvenance, DicomFile, DicomStudy
from MiqaResearch.etl_datatypes.exceptions import EtlDatatypeError, EtlLoadError
from MiqaResearch.etl_datatypes.registry import LoadResult
from MiqaResearch.readers.participant_keys import participant_alias_of
from mires_etl.schemas.dicom_instance import DicomInstanceRowSchema

from . import derived_provenance, frame_index, records
from . import storage as storage_stage
from .metadata_dump import build_metadata_dump
from .pseudonymize import pseudonymize_model

logger = logging.getLogger(__name__)

DUPLICATE_HANDLING_INHERIT = "inherit"
_RT_TYPES = {"rtstruct": "RTSTRUCT", "rtplan": "RTPLAN", "rtdose": "RTDOSE", "rtimage": "RTIMAGE"}


class _Config:
    def __init__(self, project, snapshot: dict | None):
        snapshot = snapshot or {}
        identifiers = snapshot.get("identifiers") or {}
        tags = [tag for tag in identifiers.get("tags") or [] if isinstance(tag, str)]
        # the first allow-listed configured tag is the Study's key; anything else is never matched on
        self.configured_tag = next((tag for tag in tags if tag in DICOM_KEY_TAG_ALLOWLIST), None)
        self.match_person_source_value = bool(identifiers.get("match_person_source_value"))
        handling = snapshot.get("duplicate_handling") or DUPLICATE_HANDLING_INHERIT
        if handling == DUPLICATE_HANDLING_INHERIT:
            handling = project.dicom_duplicate_handling
        self.update_duplicates = handling == "update"


def load_dicom_instances(*, project, etl_job, rows: list[DicomInstanceRowSchema], inputs):
    """Load one Job's rows; returns a `LoadResult`. Raises `EtlLoadError` (or another `EtlDatatypeError`)."""
    written: list[str] = []
    try:
        return _load(project, etl_job, rows, inputs, written)
    except BaseException as exc:
        _delete_blobs(written)
        if isinstance(exc, EtlDatatypeError):
            raise
        if isinstance(exc, ParticipantKeyError | ValueError):
            raise EtlLoadError(f"Participant Key resolution failed: {exc}") from exc
        if isinstance(exc, Exception):
            logger.exception("dicom_instance load failed for Job %s", etl_job.id)
            raise EtlLoadError(f"DICOM load failed ({type(exc).__name__}); nothing was stored.") from exc
        raise


def _delete_blobs(names: list[str]) -> None:
    storage = DicomFile._meta.get_field("file").storage
    for name in names:
        try:
            storage.delete(name)
        except Exception:
            logger.exception("Could not delete blob %s after a failed load", name)


def _load(project, etl_job, rows, inputs, written):
    config = _Config(project, etl_job.config_snapshot)
    counts = Counter()
    kept: list[str] = []
    log: list[str] = []
    skip_reasons: Counter = Counter()

    ok_rows = []
    for row in rows:
        inputs.record(row.source_path)  # an unrecorded path fails the Job
        if row.status == "skipped":
            counts["skipped"] += 1
            kept.append(row.source_path)
            skip_reasons[row.skip_reason] += 1
        else:
            ok_rows.append(row)
    for reason, count in sorted(skip_reasons.items()):
        log.append(f"{count} input(s) skipped ({reason}); left in the source")

    study_keys = _resolve_study_keys(project, etl_job, ok_rows, config)
    identical = 0
    for row in ok_rows:
        outcome = _load_file(project, etl_job, row, inputs, config, study_keys[row.study_instance_uid], written)
        if outcome == "created" or outcome == "updated":
            counts[outcome] += 1
        elif outcome == "identical":
            identical += 1
        else:  # kept: differing duplicate in skip mode
            counts["skipped"] += 1
            kept.append(row.source_path)
            log.append(
                f"skipped differing duplicate of SOP Instance {pseudonymize_uid(row.sop_instance_uid, project)}; "
                "left in the source")
    if identical:
        log.append(f"{identical} identical duplicate(s) ignored")
    return LoadResult(
        created=counts["created"], updated=counts["updated"], skipped=counts["skipped"],
        kept_inputs=tuple(kept), log_lines=tuple(log))


def _identifier_values(row) -> dict:
    return {keyword: value.split("\\") for keyword, value in row.identifiers.items()}


def _resolve_study_keys(project, etl_job, ok_rows, config) -> dict:
    by_study: dict[str, list] = {}
    for row in ok_rows:
        by_study.setdefault(row.study_instance_uid, []).append(_identifier_values(row))
    keys = {}
    for study_uid, instances in by_study.items():
        key = link_study_keys(
            project, instances, configured_tag=config.configured_tag,
            match_person_source_value=config.match_person_source_value, job=etl_job)
        keys[study_uid] = _consistent_with_stored_study(key, pseudonymize_uid(study_uid, project))
    return keys


def _consistent_with_stored_study(key, study_pseudonym: str):
    """A Study already stored keeps its key; a different one must belong to the same participant."""
    existing = DicomStudy.objects.select_related("participant_key").filter(study_instance_uid=study_pseudonym).first()
    if existing is None or existing.participant_key_id == key.pk:
        return key
    stored = existing.participant_key
    if stored.study_participant_id is not None and stored.study_participant_id == key.study_participant_id:
        return stored
    raise EtlLoadError("A Study is already stored under a different Participant Key.")


def _read_original(inputs, row) -> tuple[bytes, str]:
    record = inputs.record(row.source_path)
    with inputs.open(row.source_path) as handle:
        data = handle.read()
    sha256 = hashlib.sha256(data).hexdigest()
    if sha256 != record.sha256:
        raise EtlLoadError("An input changed after it was staged (sha256 mismatch).")
    return data, sha256


def _parse_matching(data: bytes, row):
    try:
        ds = pydicom.dcmread(io.BytesIO(data), force=True, stop_before_pixels=True)
    except Exception as exc:
        raise EtlLoadError("An input listed as DICOM could not be parsed.") from exc
    for keyword, expected in (
        ("StudyInstanceUID", row.study_instance_uid),
        ("SeriesInstanceUID", row.series_instance_uid),
        ("SOPInstanceUID", row.sop_instance_uid),
    ):
        if str(ds.get(keyword) or "").strip() != expected:
            raise EtlLoadError("A row's UIDs do not match the file's own UIDs.")
    return ds


def _assert_plausible_pixels(row) -> None:
    payload = row.payload
    limits = [
        ("Rows", row.rows, settings.DICOM_MAX_PIXEL_DIMENSIONS),
        ("Columns", row.columns, settings.DICOM_MAX_PIXEL_DIMENSIONS),
        ("NumberOfFrames", row.number_of_frames, settings.DICOM_MAX_FRAME_COUNT),
    ]
    if payload.kind == "wsi":
        limits += [
            ("TotalPixelMatrixRows", payload.total_pixel_matrix_rows, settings.DICOM_MAX_PIXEL_DIMENSIONS),
            ("TotalPixelMatrixColumns", payload.total_pixel_matrix_columns, settings.DICOM_MAX_PIXEL_DIMENSIONS),
        ]
    for name, value, maximum in limits:
        if value is not None and value > maximum:
            raise EtlLoadError(f"Declared {name}={value} exceeds the configured maximum of {maximum}.")


def _payload_metadata(row, project) -> dict:
    payload = pseudonymize_model(row.payload, project)
    kind = payload.pop("kind")
    if kind == "rdsr":
        return {"dose_report": payload}
    if kind in _RT_TYPES:
        return {"rt_summary": {"type": _RT_TYPES[kind], **payload}}
    if kind == "wsi":
        return {"pathology_summary": payload}
    return {}


def _extracted(row, ds, project, etl_job, participant_key) -> dict:
    study_datetime = row.study_datetime or etl_job.started_at or timezone.now()
    if timezone.is_naive(study_datetime):
        study_datetime = study_datetime.replace(tzinfo=UTC)
    pseudonymized = pseudonymize_model(row, project)
    metadata = build_metadata_dump(ds, project, participant_alias_of(participant_key))
    metadata.update(_payload_metadata(row, project))
    return {
        "study_datetime": study_datetime,
        "study_description": row.study_description,
        "series_description": row.series_description,
        "modality": row.modality,
        "contains_burned_in_annotations": row.contains_burned_in_annotations,
        "image_orientation_patient": row.image_orientation_patient,
        "image_position_patient": row.image_position_patient,
        "pixel_spacing": row.pixel_spacing,
        "frame_of_reference_uid": pseudonymized["frame_of_reference_uid"],
        "metadata": metadata,
    }


def _set_frame_index(dcm_file: DicomFile, data: bytes) -> None:
    try:
        index = frame_index.build_frame_index(io.BytesIO(data))
    except Exception:
        # never fail a load over the index: it is rebuilt on first /frames request or by the backfill
        logger.exception("Could not build the frame offset index for %s", dcm_file.sop_instance_uid)
        return
    dcm_file.transfer_syntax_uid = index.transfer_syntax_uid or None
    dcm_file.frame_index = index.frames


def _stored_sha256(dcm_file: DicomFile) -> str:
    if dcm_file.content_sha256:
        return dcm_file.content_sha256
    with dcm_file.file.storage.open(dcm_file.file.name, "rb") as stored:
        return hashlib.sha256(stored.read()).hexdigest()


def _verify(dcm_file: DicomFile, sha256: str) -> None:
    if not storage_stage.verify_stored_bytes(dcm_file, sha256):
        raise EtlLoadError("A stored blob did not read back identically (sha256 mismatch).")


def _load_file(project, etl_job, row, inputs, config, participant_key, written) -> str:
    """Returns "created", "updated", "identical" or "kept"."""
    _assert_plausible_pixels(row)
    data, sha256 = _read_original(inputs, row)
    ds = _parse_matching(data, row)
    pseudonyms = {
        "study": pseudonymize_uid(row.study_instance_uid, project),
        "series": pseudonymize_uid(row.series_instance_uid, project),
        "sop": pseudonymize_uid(row.sop_instance_uid, project),
    }
    size_mb = len(data) / (1024 * 1024)

    existing = DicomFile.objects.select_related("series__study__participant_key__study_participant") \
        .filter(sop_instance_uid=pseudonyms["sop"]).first()
    if existing is not None:
        if sha256 == _stored_sha256(existing):
            return "identical"
        if not config.update_duplicates:
            return "kept"
        extracted = _extracted(row, ds, project, etl_job, existing.series.study.participant_key)
        superseded = storage_stage.replace_file_bytes(existing, data)
        written.append(existing.file.name)
        _set_frame_index(existing, data)
        records.update_file_in_place(existing, extracted, size_mb, sha256)
        records.fill_study_series_blanks(existing.series, extracted)
        transaction.on_commit(lambda: storage_stage.discard_file(existing, superseded))
        _verify(existing, sha256)
        return "updated"

    extracted = _extracted(row, ds, project, etl_job, participant_key)
    dcm_file = records.build_hierarchy(participant_key, project, pseudonyms, extracted, size_mb)
    dcm_file.content_sha256 = sha256
    _set_frame_index(dcm_file, data)
    storage_stage.store_file_bytes(dcm_file, data)
    written.append(dcm_file.file.name)
    dcm_file.save()
    records.add_file_size_to_series(dcm_file.series, size_mb)
    records.set_series_frame_of_reference(dcm_file.series)
    derived_provenance.record_ingested_provenance(dcm_file, ds, project)
    _link_referencing_derived_objects(dcm_file.series)
    _verify(dcm_file, sha256)
    return "created"


def _link_referencing_derived_objects(series) -> None:
    """An RTSTRUCT stored earlier (another Job) that references this series gets it as a source series,
    so an RT chain links the same whichever order its objects arrive in."""
    key = series.series_instance_uid
    participant_key = series.study.participant_key
    owner = (
        {"series__study__participant_key__study_participant_id": participant_key.study_participant_id}
        if participant_key.study_participant_id
        else {"series__study__participant_key_id": participant_key.pk}
    )
    referencing = DicomFile.objects.filter(
        metadata__rt_summary__referenced_series_instance_uids__contains=[key], **owner
    ).exclude(series=series)
    for dcm_file in referencing:
        provenance = DerivedObjectProvenance.objects.filter(series=dcm_file.series).first()
        if provenance is not None:
            provenance.source_series.add(series)

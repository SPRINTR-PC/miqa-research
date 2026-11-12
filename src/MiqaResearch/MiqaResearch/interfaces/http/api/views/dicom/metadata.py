"""WADO-RS Retrieve Metadata, served through the De-identification Profile (#275).

Each instance's stored header is parsed (pixel data skipped), de-identified
with the shared sanitizer (`helpers.dicom_deidentification`, ADR 0028), then
serialized with `to_json_dict()`. The stored bytes stay original; UIDs come
out as the HashUID pseudonyms the DB rows and frame URLs use. The stored
transfer syntax is added as AvailableTransferSyntaxUID (0008,3002).
"""
import io
import json

import pydicom
from django.http import HttpResponse
from ninja import Router

from helpers.dicom_deidentification import deidentify
from MiqaResearch.data.models.dicom_file import DicomFile
from MiqaResearch.readers.participant_keys import participant_alias_of

from .access import audited_files, not_for_sessions, readable_dicom_files
from .caching import METADATA_CACHE_CONTROL, matches_if_none_match, not_modified, strong_etag, with_cache_headers

router = Router()

_AVAILABLE_TRANSFER_SYNTAX_UID = "00083002"


@router.get("/studies/{study_instance_uid}/metadata")
@not_for_sessions
def retrieve_study_metadata(request, study_instance_uid: str):
    return _metadata_response(request, _files(request).filter(series__study__study_instance_uid=study_instance_uid))


@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}/metadata")
def retrieve_series_metadata(request, study_instance_uid: str, series_instance_uid: str):
    return _metadata_response(
        request,
        _files(request).filter(
            series__series_instance_uid=series_instance_uid,
            series__study__study_instance_uid=study_instance_uid,
        ),
        series_open=True,
    )


@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances/{sop_instance_uid}/metadata")
@not_for_sessions
def retrieve_instance_metadata(request, study_instance_uid: str, series_instance_uid: str, sop_instance_uid: str):
    return _metadata_response(
        request,
        _files(request).filter(
            sop_instance_uid=sop_instance_uid,
            series__series_instance_uid=series_instance_uid,
            series__study__study_instance_uid=study_instance_uid,
        )
    )


def _files(request):
    return readable_dicom_files(
        request, "research_project", "series__study__participant_key__project"
    ).order_by("series_id", "pk")


def _metadata_response(request, dicom_files, *, series_open: bool = False):
    dicom_files = audited_files(request, dicom_files, series_open=series_open)
    if not dicom_files:
        return HttpResponse(status=404)
    instances = [sanitized_instance_json(dicom_file) for dicom_file in dicom_files]
    body = json.dumps(instances, separators=(",", ":")).encode()
    etag = strong_etag(body)
    if matches_if_none_match(request, etag):
        return not_modified(etag, METADATA_CACHE_CONTROL)
    return with_cache_headers(HttpResponse(body, content_type="application/json"), etag, METADATA_CACHE_CONTROL)


def sanitized_instance_json(dicom_file: DicomFile) -> dict:
    """DICOM JSON (PS3.18 F.2) of one stored instance's de-identified header."""
    key = dicom_file.series.study.participant_key
    research_project = dicom_file.research_project or key.project
    header = _stored_header(dicom_file)
    sanitized = deidentify(
        header, research_project=research_project, participant_alias=participant_alias_of(key),
        # viewer-saved Annotations/Segmentations (#287) are stored with pseudonymized UIDs already
        uids_already_pseudonymized=dicom_file.uids_pseudonymized,
    )
    instance = sanitized.to_json_dict()
    transfer_syntax_uid = dicom_file.transfer_syntax_uid or _stored_transfer_syntax(header)
    if transfer_syntax_uid:
        instance[_AVAILABLE_TRANSFER_SYNTAX_UID] = {"vr": "UI", "Value": [transfer_syntax_uid]}
    return instance


def _stored_header(dicom_file: DicomFile):
    """The stored file's header, pixel data skipped.

    With a frame offset index, everything up to the first frame is one ranged
    read (the Pixel Data element header lies before it); otherwise, or if that
    prefix doesn't parse, the whole file is read.
    """
    if dicom_file.frame_index:
        prefix = dicom_file.file.storage.read_range(dicom_file.file.name, 0, dicom_file.frame_index[0][0])
        try:
            return pydicom.dcmread(io.BytesIO(prefix), stop_before_pixels=True)
        except Exception:  # noqa: BLE001 - fall back to the whole file
            pass
    with dicom_file.file.open("rb") as stored:
        return pydicom.dcmread(stored, stop_before_pixels=True)


def _stored_transfer_syntax(header) -> str | None:
    file_meta = getattr(header, "file_meta", None)
    return str(file_meta.TransferSyntaxUID) if file_meta is not None and "TransferSyntaxUID" in file_meta else None

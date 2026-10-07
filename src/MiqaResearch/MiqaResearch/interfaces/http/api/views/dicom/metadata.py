"""WADO-RS Retrieve Metadata, served through the De-identification Profile (#275).

Each instance's stored header is parsed (pixel data skipped), de-identified
with the shared sanitizer (`helpers.dicom_deidentification`, ADR 0028), then
serialized with `to_json_dict()`. The stored bytes stay original; UIDs come
out as the HashUID pseudonyms the DB rows and frame URLs use. The stored
transfer syntax is added as AvailableTransferSyntaxUID (0008,3002).
"""
import pydicom
from django.http import HttpResponse
from ninja import Router

from helpers.dicom_deidentification import deidentify
from MiqaResearch.data.models.dicom_file import DicomFile

router = Router()

_AVAILABLE_TRANSFER_SYNTAX_UID = "00083002"


@router.get("/studies/{study_instance_uid}/metadata")
def retrieve_study_metadata(request, study_instance_uid: str):
    return _metadata_response(_files().filter(series__study__study_instance_uid=study_instance_uid))


@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}/metadata")
def retrieve_series_metadata(request, study_instance_uid: str, series_instance_uid: str):
    return _metadata_response(
        _files().filter(
            series__series_instance_uid=series_instance_uid,
            series__study__study_instance_uid=study_instance_uid,
        )
    )


@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances/{sop_instance_uid}/metadata")
def retrieve_instance_metadata(request, study_instance_uid: str, series_instance_uid: str, sop_instance_uid: str):
    return _metadata_response(
        _files().filter(
            sop_instance_uid=sop_instance_uid,
            series__series_instance_uid=series_instance_uid,
            series__study__study_instance_uid=study_instance_uid,
        )
    )


def _files():
    return DicomFile.objects.select_related(
        "research_project", "series__study__study_participant__research_project"
    ).order_by("series_id", "pk")


def _metadata_response(dicom_files):
    instances = [sanitized_instance_json(dicom_file) for dicom_file in dicom_files]
    if not instances:
        return HttpResponse(status=404)
    return instances


def sanitized_instance_json(dicom_file: DicomFile) -> dict:
    """DICOM JSON (PS3.18 F.2) of one stored instance's de-identified header."""
    participant = dicom_file.series.study.study_participant
    research_project = dicom_file.research_project or participant.research_project
    with dicom_file.file.open("rb") as stored:
        header = pydicom.dcmread(stored, stop_before_pixels=True)
    sanitized = deidentify(
        header, research_project=research_project, participant_alias=participant.alias1,
        # viewer-saved Annotations/Segmentations (#287) are stored with pseudonymized UIDs already
        uids_already_pseudonymized=dicom_file.uids_pseudonymized,
    )
    instance = sanitized.to_json_dict()
    transfer_syntax_uid = dicom_file.transfer_syntax_uid or _stored_transfer_syntax(header)
    if transfer_syntax_uid:
        instance[_AVAILABLE_TRANSFER_SYNTAX_UID] = {"vr": "UI", "Value": [transfer_syntax_uid]}
    return instance


def _stored_transfer_syntax(header) -> str | None:
    file_meta = getattr(header, "file_meta", None)
    return str(file_meta.TransferSyntaxUID) if file_meta is not None and "TransferSyntaxUID" in file_meta else None

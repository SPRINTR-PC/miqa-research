"""WADO-RS Retrieve Frames (#274).

Frames are served in the stored transfer syntax, never transcoded: one ranged
read per frame via the DicomFile's frame offset index
(tasks/dicom_handling/frame_index.py), no server-side frame cache. Each part
carries the syntax's media type plus ``transfer-syntax=<uid>``; an Accept that
can't be satisfied gets 406.
"""
import re

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router
from pydicom.uid import UID

from MiqaResearch.data.models.dicom_file import DicomFile
from MiqaResearch.tasks.dicom_handling.frame_index import build_frame_index, frame_bytes

from .access import audit_access, readable_files
from .caching import FRAMES_CACHE_CONTROL, matches_if_none_match, not_modified, strong_etag, with_cache_headers

router = Router()

OCTET_STREAM = "application/octet-stream"

# Media type per encapsulated transfer syntax (PS3.18 Table 8.7.3-5); native → octet-stream.
_MEDIA_TYPES = {
    "1.2.840.10008.1.2.4.50": "image/jpeg",
    "1.2.840.10008.1.2.4.51": "image/jpeg",
    "1.2.840.10008.1.2.4.57": "image/jpeg",
    "1.2.840.10008.1.2.4.70": "image/jpeg",
    "1.2.840.10008.1.2.4.80": "image/jls",
    "1.2.840.10008.1.2.4.81": "image/jls",
    "1.2.840.10008.1.2.4.90": "image/jp2",
    "1.2.840.10008.1.2.4.91": "image/jp2",
    "1.2.840.10008.1.2.4.92": "image/jpx",
    "1.2.840.10008.1.2.4.93": "image/jpx",
    "1.2.840.10008.1.2.4.201": "image/jphc",
    "1.2.840.10008.1.2.4.202": "image/jphc",
    "1.2.840.10008.1.2.4.203": "image/jphc",
    "1.2.840.10008.1.2.4.110": "image/jxl",
    "1.2.840.10008.1.2.4.111": "image/jxl",
    "1.2.840.10008.1.2.4.112": "image/jxl",
    "1.2.840.10008.1.2.5": "image/dicom-rle",
}

_SPLIT_OUTSIDE_QUOTES = r'{}(?=(?:[^"]*"[^"]*")*[^"]*$)'


def media_type_for(transfer_syntax_uid: str) -> str:
    return _MEDIA_TYPES.get(transfer_syntax_uid, OCTET_STREAM)


def accepts(accept_header: str | None, media_type: str, transfer_syntax_uid: str) -> bool:
    """Whether the Accept header admits frames of `media_type` in `transfer_syntax_uid`.

    Only multipart/related responses are produced. A missing ``transfer-syntax``
    parameter admits whatever syntax the stored media type is in;
    ``type="application/octet-stream"; transfer-syntax=*`` admits anything
    (what dicom-microscopy-viewer and Cornerstone3D send).
    """
    if not accept_header or not accept_header.strip():
        return True
    for media_range in re.split(_SPLIT_OUTSIDE_QUOTES.format(","), accept_header):
        main, params = _parse_media_range(media_range)
        if params.get("q", "1").strip() in ("0", "0.0", "0.00", "0.000"):
            continue
        if main == "*/*":
            return True
        if main not in ("multipart/related", "multipart/*"):
            continue
        part_type = params.get("type", OCTET_STREAM).lower()
        syntax = params.get("transfer-syntax")
        if part_type == OCTET_STREAM and syntax == "*":
            return True
        if part_type in ("*/*", media_type) or (part_type.endswith("/*") and media_type.startswith(part_type[:-1])):
            if syntax in (None, "*", transfer_syntax_uid):
                return True
    return False


def _parse_media_range(media_range: str) -> tuple[str, dict[str, str]]:
    pieces = [piece.strip() for piece in re.split(_SPLIT_OUTSIDE_QUOTES.format(";"), media_range)]
    params = {}
    for piece in pieces[1:]:
        key, _, value = piece.partition("=")
        params[key.strip().lower()] = value.strip().strip('"')
    return pieces[0].lower(), params


@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances/{sop_instance_uid}/frames/{frame_list}")
def retrieve_frames(request, study_instance_uid: str, series_instance_uid: str, sop_instance_uid: str, frame_list: str):
    try:
        frame_numbers = [int(number) for number in frame_list.split(",")]
    except ValueError:
        return HttpResponse("Invalid frame list", status=400)

    # One query: the file, its frame offset index and Participant Visibility / the Client Binding.
    dicom_file = get_object_or_404(
        readable_files(request, DicomFile.objects.select_related("series__study__study_participant")),
        sop_instance_uid=sop_instance_uid,
        series__series_instance_uid=series_instance_uid,
        series__study__study_instance_uid=study_instance_uid,
    )
    audit_access(request, [dicom_file])
    _ensure_frame_index(dicom_file)
    frames = dicom_file.frame_index
    if not frames:
        return HttpResponse("No servable frames in this instance", status=404)

    transfer_syntax_uid = dicom_file.transfer_syntax_uid
    media_type = media_type_for(transfer_syntax_uid)
    if not accepts(request.headers.get("Accept"), media_type, transfer_syntax_uid):
        return HttpResponse(
            f"Frames are only available as {media_type} in transfer syntax {transfer_syntax_uid}", status=406
        )
    for number in frame_numbers:
        if not 1 <= number <= len(frames):
            return HttpResponse(f"Frame number {number} out of range", status=404)

    # Strong ETag: same stored bytes + same frame list -> byte-identical body (the boundary derives from it).
    etag = strong_etag(dicom_file.content_sha256 or dicom_file.file.name, transfer_syntax_uid, frame_list)
    if matches_if_none_match(request, etag):
        return not_modified(etag, FRAMES_CACHE_CONTROL, vary=("Accept",))

    encapsulated = UID(transfer_syntax_uid).is_encapsulated
    storage, name = dicom_file.file.storage, dicom_file.file.name
    payloads = [frame_bytes(storage.read_range(name, *frames[number - 1]), encapsulated) for number in frame_numbers]
    response = _multipart_related(
        payloads, f"{media_type}; transfer-syntax={transfer_syntax_uid}", media_type, boundary=etag.strip('"')[:32]
    )
    return with_cache_headers(response, etag, FRAMES_CACHE_CONTROL, vary=("Accept",))


def _ensure_frame_index(dicom_file: DicomFile) -> None:
    """Build and persist a missing index (rows the backfill hasn't reached yet); reads the whole file once."""
    if dicom_file.frame_index is not None:
        return
    with dicom_file.file.open("rb") as stored:
        index = build_frame_index(stored)
    dicom_file.transfer_syntax_uid = index.transfer_syntax_uid or None
    dicom_file.frame_index = index.frames
    dicom_file.save(update_fields=["transfer_syntax_uid", "frame_index"])


def _multipart_related(payloads: list[bytes], part_content_type: str, media_type: str, boundary: str) -> HttpResponse:
    body = b"".join(
        f"--{boundary}\r\nContent-Type: {part_content_type}\r\n\r\n".encode() + payload + b"\r\n"
        for payload in payloads
    ) + f"--{boundary}--\r\n".encode()
    return HttpResponse(body, content_type=f'multipart/related; type="{media_type}"; boundary={boundary}')

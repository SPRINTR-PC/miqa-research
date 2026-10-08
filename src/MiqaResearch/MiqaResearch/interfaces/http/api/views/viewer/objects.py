"""Viewer API for Annotations and Segmentations (ADR 0026, #287). Session auth only (CSRF on POST).

- POST /objects: multipart `file` (the browser-built SR or SEG), `source_series` (one or more
  Series Instance UIDs, base series first) and optional `supersedes` (the head id the user edited).
  201 with the new version; 409 with the current head when `supersedes` is stale.
- GET /objects?participant=<id>[&series=<uid>][&include_retired=true]: version chains.
- POST /objects/{id}/retire: retires the chain through its head; 409 with the head when stale.

Unknown or invisible participants, series and objects are 404 alike.
"""
from datetime import datetime
from uuid import UUID

from ninja import File, Form, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.security import SessionAuth

from MiqaResearch.actions.annotations import (
    InvalidObject,
    NotAllowed,
    NotFound,
    StaleHead,
    retire_object,
    save_viewer_object,
)
from MiqaResearch.readers.annotation_reader import ParticipantNotVisible, list_participant_objects, version_item

router = Router(auth=SessionAuth(), tags=["viewer"])

_REFUSALS = (InvalidObject, NotAllowed, NotFound)


class VersionOut(Schema):
    id: UUID
    chain_id: UUID
    kind: str
    source: str
    version: int
    series_instance_uid: str
    series_description: str | None
    modality: str | None
    author: str | None
    created_at: datetime
    retired: bool
    source_series_uids: list[str]


class ChainOut(VersionOut):
    can_change: bool
    history: list[VersionOut]


class ConflictOut(Schema):
    detail: str
    head: VersionOut


class ErrorOut(Schema):
    detail: str


@router.post(
    "/objects",
    response={201: VersionOut, 400: ErrorOut, 403: ErrorOut, 404: ErrorOut, 409: ConflictOut},
    url_name="viewer_object_save",
)
def save_object(
    request,
    file: File[UploadedFile],
    source_series: Form[list[str]],
    supersedes: Form[UUID | None] = None,
):
    try:
        provenance = save_viewer_object(
            user=request.auth,
            raw_bytes=file.read(),
            source_series_uids=source_series,
            supersedes=supersedes,
            request=request,
        )
    except StaleHead as stale:
        return Status(409, {"detail": "a newer version was saved first", "head": version_item(stale.head)})
    except _REFUSALS as error:
        raise _http_error(error) from None
    return Status(201, version_item(provenance))


@router.get("/objects", response=list[ChainOut], url_name="viewer_object_list")
def list_objects(request, participant: UUID, series: str | None = None, include_retired: bool = False):
    try:
        return list_participant_objects(request.auth, participant, series, include_retired, request.session)
    except ParticipantNotVisible:
        raise HttpError(404, "Not Found") from None


@router.post(
    "/objects/{object_id}/retire",
    response={200: VersionOut, 403: ErrorOut, 404: ErrorOut, 409: ConflictOut},
    url_name="viewer_object_retire",
)
def retire(request, object_id: UUID):
    try:
        provenance = retire_object(user=request.auth, object_id=object_id, request=request)
    except StaleHead as stale:
        return Status(409, {"detail": "a newer version was saved; retire the head", "head": version_item(stale.head)})
    except _REFUSALS as error:
        raise _http_error(error) from None
    return Status(200, version_item(provenance))



def _http_error(error: Exception) -> HttpError:
    if isinstance(error, NotFound):
        return HttpError(404, "Not Found")
    if isinstance(error, NotAllowed):
        return HttpError(403, str(error))
    return HttpError(400, str(error))

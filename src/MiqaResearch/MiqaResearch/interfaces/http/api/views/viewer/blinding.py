"""Viewer API for Blinded Annotation (ADR 0026, #288). Session auth only (CSRF on PUT/POST).

- PUT /projects/{id}/blinded-annotation {"blinded": bool}: PI or Project Admin turn the flag on/off.
- GET /participants/{id}/blinding: flag, this Viewer Session's reveal, whether the caller may reveal, hidden count.
- POST /participants/{id}/blinding-reveal: a Blinding Reveal for this participant and Viewer Session
  (`X-Mires-Viewer-Session`, sent by the viewer on each request; 400 without it).

Unknown or invisible projects and participants are 404 alike; 403 for roles that may not; 400 for a
reveal on a project without Blinded Annotation.
"""
from uuid import UUID

from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import SessionAuth

from MiqaResearch.actions.blinding import reveal_participant, set_blinded_annotation
from MiqaResearch.actions.viewer_exceptions import ViewerActionError
from MiqaResearch.readers.annotation_reader import participant_blinding_status
from MiqaResearch.readers.blinding import viewer_reveals
from MiqaResearch.readers.participant_visibility import ParticipantNotVisible

from .errors import ErrorOut, http_error

router = Router(auth=SessionAuth(), tags=["viewer"])


class FlagIn(Schema):
    blinded: bool


class FlagOut(Schema):
    blinded: bool


class BlindingOut(Schema):
    blinded: bool
    revealed: bool
    can_reveal: bool
    hidden: int


@router.put(
    "/projects/{project_id}/blinded-annotation",
    response={200: FlagOut, 403: ErrorOut, 404: ErrorOut},
    url_name="viewer_blinded_annotation",
)
def set_flag(request, project_id: UUID, payload: FlagIn):
    try:
        project = set_blinded_annotation(
            user=request.auth, project_id=project_id, blinded=payload.blinded, request=request)
    except ViewerActionError as error:
        raise http_error(error) from None
    return {"blinded": project.blinded_annotation}


@router.get("/participants/{participant_id}/blinding", response=BlindingOut, url_name="viewer_blinding")
def blinding_status(request, participant_id: UUID):
    try:
        return participant_blinding_status(request.auth, participant_id, viewer_reveals(request))
    except ParticipantNotVisible:
        raise HttpError(404, "Not Found") from None


@router.post(
    "/participants/{participant_id}/blinding-reveal",
    response={200: BlindingOut, 400: ErrorOut, 403: ErrorOut, 404: ErrorOut},
    url_name="viewer_blinding_reveal",
)
def reveal(request, participant_id: UUID):
    try:
        reveal_participant(user=request.auth, participant_id=participant_id, request=request)
    except ViewerActionError as error:
        raise http_error(error) from None
    return participant_blinding_status(request.auth, participant_id, viewer_reveals(request))

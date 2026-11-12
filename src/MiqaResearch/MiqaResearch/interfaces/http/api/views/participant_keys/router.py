"""Participant Key tracking view and Admin actions (#422, ADR 0035). Session auth; backend for the Data tab section.

- GET  /projects/{id}/keys: Data Table (type, masked value, linked, participant alias, Study/Series counts, first
  seen; filters `linked`, `key_type`). `reveal=true&reason=<pick-list code>` shows values: an audited Identity Reveal.
- GET  /projects/{id}/participant-search?q=: alias search (id + alias only) within Participant Visibility.
- POST /keys/{key_id}/link: Admin or Data Manager. POST .../repoint and .../unlink: Admin only, reason required.

Admin and Data Manager only; unknown project or no role on it is 404, a lower role 403, bad input 400.
"""
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.pagination import paginate
from ninja.security import SessionAuth

from contract.constants.audit_log import EVENT_TYPE_PID_VIEW
from contract.constants.participant_key import REVEAL_REASON_CHOICES
from MiqaResearch.actions.participant_key_admin import link_key, repoint_key, unlink_key
from MiqaResearch.actions.viewer_exceptions import ViewerActionError
from MiqaResearch.data.models import AuditLog, ParticipantKey, ResearchProject, ResearchProjectUserRoleMap
from MiqaResearch.interfaces.http.api.pagination import DataTablePagination
from MiqaResearch.interfaces.http.api.views.viewer.errors import ErrorOut, http_error
from MiqaResearch.readers.participant_keys import key_table_source, search_participants
from MiqaResearch.readers.participant_visibility import can_open_unlinked

router = Router(auth=SessionAuth(), tags=["participant-keys"])

_REVEAL_REASONS = {value for value, _ in REVEAL_REASON_CHOICES}


class ParticipantRef(Schema):
    participant_id: UUID | None = None
    person_source_value: str | None = None
    reveal_reason: str | None = None


class LinkIn(ParticipantRef):
    fill_demographics: bool = False


class RepointIn(ParticipantRef):
    reason: str


class UnlinkIn(Schema):
    reason: str


class KeyOut(Schema):
    id: UUID
    key_type: str
    linked: bool
    participant_id: UUID | None


class LinkOut(KeyOut):
    changed: bool
    demographics_filled: list[str]
    demographics_mismatched: list[str]


class ParticipantHit(Schema):
    id: UUID
    alias: str


def _key_out(key: ParticipantKey) -> dict:
    return {
        "id": key.pk, "key_type": key.key_type, "linked": key.study_participant_id is not None,
        "participant_id": key.study_participant_id,
    }


def _tracking_project(user, project_id: UUID) -> ResearchProject:
    """The project, if `user` may use the tracking view (Admin, Data Manager, superuser): 404 without any role
    on it, 403 with a lower role."""
    project = ResearchProject.objects.filter(pk=project_id).first()
    if project is None:
        raise HttpError(404, "Not Found")
    if not (user.is_superuser or ResearchProjectUserRoleMap.objects.filter(user=user, project=project).exists()):
        raise HttpError(404, "Not Found")
    if not can_open_unlinked(user, project):
        raise HttpError(403, "only a project Admin or Data Manager may use Participant Keys")
    return project


@router.get("/projects/{project_id}/keys", response=list[dict[str, Any]], url_name="participant_key_table")
@paginate(DataTablePagination)
async def key_table(request, project_id: UUID, reveal: bool = False, reason: str | None = None):
    user = await request.auser()
    project = await sync_to_async(_tracking_project)(user, project_id)
    if reveal and reason not in _REVEAL_REASONS:
        raise HttpError(400, "a valid reason is required to reveal key values")
    source = key_table_source(user, project, reveal=reveal)
    if reveal:
        await sync_to_async(AuditLog.objects.record)(
            EVENT_TYPE_PID_VIEW, user=user, request=request, project=project,
            metadata={"project_id": str(project.pk), "purpose": "participant_key_table", "reason": reason})
    return source


@router.get(
    "/projects/{project_id}/participant-search", response=list[ParticipantHit],
    url_name="participant_key_participant_search")
def participant_search(request, project_id: UUID, q: str):
    project = _tracking_project(request.auth, project_id)
    return search_participants(request.auth, project, q)


@router.post(
    "/keys/{key_id}/link", response={200: LinkOut, 400: ErrorOut, 403: ErrorOut, 404: ErrorOut},
    url_name="participant_key_link")
def link(request, key_id: UUID, payload: LinkIn):
    try:
        result = link_key(
            user=request.auth, key_id=key_id, participant_id=payload.participant_id,
            person_source_value=payload.person_source_value, reveal_reason=payload.reveal_reason,
            fill_demographics=payload.fill_demographics, request=request)
    except ViewerActionError as error:
        raise http_error(error) from None
    return {
        **_key_out(result["key"]), "changed": result["changed"],
        "demographics_filled": result["demographics"]["filled"],
        "demographics_mismatched": result["demographics"]["mismatched"],
    }


@router.post(
    "/keys/{key_id}/repoint", response={200: KeyOut, 400: ErrorOut, 403: ErrorOut, 404: ErrorOut},
    url_name="participant_key_repoint")
def repoint(request, key_id: UUID, payload: RepointIn):
    try:
        key = repoint_key(
            user=request.auth, key_id=key_id, reason=payload.reason, participant_id=payload.participant_id,
            person_source_value=payload.person_source_value, reveal_reason=payload.reveal_reason, request=request)
    except ViewerActionError as error:
        raise http_error(error) from None
    return _key_out(key)


@router.post(
    "/keys/{key_id}/unlink", response={200: KeyOut, 400: ErrorOut, 403: ErrorOut, 404: ErrorOut},
    url_name="participant_key_unlink")
def unlink(request, key_id: UUID, payload: UnlinkIn):
    try:
        key = unlink_key(user=request.auth, key_id=key_id, reason=payload.reason, request=request)
    except ViewerActionError as error:
        raise http_error(error) from None
    return _key_out(key)

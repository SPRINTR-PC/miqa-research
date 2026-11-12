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
from ninja.pagination import paginate
from ninja.security import SessionAuth
from pydantic import field_validator

from contract.constants.participant_key import MAX_REASON_LENGTH
from MiqaResearch.actions.participant_key_admin import (
    link_key,
    open_key_table,
    repoint_key,
    tracking_project,
    unlink_key,
)
from MiqaResearch.actions.viewer_exceptions import ViewerActionError
from MiqaResearch.data.models import ParticipantKey
from MiqaResearch.interfaces.http.api.pagination import DataTablePagination
from MiqaResearch.interfaces.http.api.views.viewer.errors import ErrorOut, http_error
from MiqaResearch.readers.participant_keys import search_participants

router = Router(auth=SessionAuth(), tags=["participant-keys"])


def _checked_reason(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("a reason is required")
    if len(value) > MAX_REASON_LENGTH:
        raise ValueError(f"the reason may be at most {MAX_REASON_LENGTH} characters")
    return value


class ParticipantRef(Schema):
    participant_id: UUID | None = None
    person_source_value: str | None = None
    reveal_reason: str | None = None


class LinkIn(ParticipantRef):
    fill_demographics: bool = False


class RepointIn(ParticipantRef):
    reason: str

    _check_reason = field_validator("reason")(_checked_reason)


class UnlinkIn(Schema):
    reason: str

    _check_reason = field_validator("reason")(_checked_reason)


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


@router.get("/projects/{project_id}/keys", response=list[dict[str, Any]], url_name="participant_key_table")
@paginate(DataTablePagination)
async def key_table(request, project_id: UUID, reveal: bool = False, reason: str | None = None):
    user = await request.auser()
    try:
        return await sync_to_async(open_key_table)(user, project_id, reveal=reveal, reason=reason, request=request)
    except ViewerActionError as error:
        raise http_error(error) from None


@router.get(
    "/projects/{project_id}/participant-search", response=list[ParticipantHit],
    url_name="participant_key_participant_search")
def participant_search(request, project_id: UUID, q: str):
    try:
        project = tracking_project(request.auth, project_id)
    except ViewerActionError as error:
        raise http_error(error) from None
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
        **_key_out(result.key), "changed": result.changed,
        "demographics_filled": result.demographics.filled,
        "demographics_mismatched": result.demographics.mismatched,
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

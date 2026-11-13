"""Admin actions on Participant Keys (#422, ADR 0035, decided in #404): link, re-point, unlink.

- Link: project Admin and Data Manager (and superusers), an unlinked key. The participant is chosen by
  `participant_id` (from the alias search) or by exact `person_source_value`, which is an audited Identity
  Reveal (`pid_view`, with a pick-list reason). Both are scoped by Participant Visibility. Optionally fills
  the participant's blank date of birth and sex from the key's stored original files.
- Re-point and unlink: project Admin only, with a required reason. The key's Studies follow through the key.

Unknown key or project, or no role on it: NotFound. Known but role too low: NotAllowed. Unknown or invisible
participant, bad input: a plain refusal (400). Every action is one audit event; no key values or identities
in metadata.
"""
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from contract.constants.audit_log import (
    EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED,
    EVENT_TYPE_PARTICIPANT_KEY_LINKED,
    EVENT_TYPE_PARTICIPANT_KEY_REPOINTED,
    EVENT_TYPE_PARTICIPANT_KEY_UNLINKED,
    EVENT_TYPE_PID_VIEW,
)
from contract.constants.participant_key import LINK_VIA_ADMIN, MAX_REASON_LENGTH, REVEAL_REASONS
from helpers.db_fields import get_deterministic_hash
from helpers.person_source_value import format_person_source_value
from MiqaResearch.actions.participant_demographics import DemographicsOutcome, fill_and_compare_demographics
from MiqaResearch.actions.viewer_exceptions import NotAllowed, NotFound, ViewerActionError
from MiqaResearch.data.models import AuditLog, ParticipantKey, ResearchProject, StudyParticipant
from MiqaResearch.readers.participant_keys import is_project_admin, key_table_source, key_with_role, project_with_role
from MiqaResearch.readers.participant_visibility import can_open_unlinked, visible_participants


class InvalidKeyAction(ViewerActionError):
    """Bad input: unknown participant, missing reason, key in the wrong state. 400 with the message."""


@dataclass(frozen=True)
class LinkResult:
    key: ParticipantKey
    changed: bool
    demographics: DemographicsOutcome = field(default_factory=DemographicsOutcome)


def tracking_project(user, project_id) -> ResearchProject:
    """The project, if `user` may use the key tracking view (Admin, Data Manager, superuser): NotFound without
    any role on it, NotAllowed with a lower role."""
    project = project_with_role(user, project_id)
    if project is None:
        raise NotFound()
    if not can_open_unlinked(user, project):
        raise NotAllowed("only a project Admin or Data Manager may use Participant Keys")
    return project


def open_key_table(user, project_id, *, reveal: bool, reason: str | None, request=None):
    """The key table source. `reveal` shows the values: an audited Identity Reveal, with a pick-list reason."""
    project = tracking_project(user, project_id)
    if reveal and reason not in REVEAL_REASONS:
        raise InvalidKeyAction("a valid reason is required to reveal key values")
    source = key_table_source(user, project, reveal=reveal)
    if reveal:
        AuditLog.objects.record(
            EVENT_TYPE_PID_VIEW, user=user, request=request, project=project,
            metadata={"project_id": str(project.pk), "purpose": "participant_key_table", "reason": reason})
    return source


def _audit(event_type, user, request, key: ParticipantKey, **metadata) -> None:
    """One audit event about `key`; ids and reasons only, never key values or identities."""
    AuditLog.objects.record(
        event_type, user=user, request=request, project=key.project, metadata={"key_id": str(key.pk), **metadata})


def link_key(
    *, user, key_id, participant_id=None, person_source_value=None, reveal_reason=None,
    fill_demographics=False, request=None,
) -> LinkResult:
    """Link an unlinked key. Linking again to the same participant is a no-op (`changed` False); another one
    is refused (re-point instead). Returns the key, `changed` and the demographics outcome (filled / mismatched).

    The participant lookup (an audited Identity Reveal when by PID) runs before the transaction, so its audit
    entry stays even when the link is then refused."""
    key = _visible_key(user, key_id)
    if not can_open_unlinked(user, key.project):
        raise NotAllowed("only a project Admin or Data Manager may link Participant Keys")
    participant = _resolve_participant(
        user, key, participant_id, person_source_value, reveal_reason, request, purpose="link")
    with transaction.atomic():
        key = _locked_key(key_id)
        if key.study_participant_id == participant.pk:
            return LinkResult(key, changed=False)
        if key.study_participant_id is not None:
            raise InvalidKeyAction("the key is already linked to another participant; re-point it")
        _set_link(key, participant)
        _audit(
            EVENT_TYPE_PARTICIPANT_KEY_LINKED, user, request, key,
            participant_id=str(participant.pk), fill_demographics=bool(fill_demographics))
        demographics = DemographicsOutcome()
        if fill_demographics:
            demographics = fill_and_compare_demographics(participant, [key])
            if demographics.filled:
                _audit(
                    EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED, user, request, key,
                    participant_id=str(participant.pk), fields=demographics.filled)
    return LinkResult(key, changed=True, demographics=demographics)


def repoint_key(
    *, user, key_id, reason, participant_id=None, person_source_value=None, reveal_reason=None, request=None,
) -> ParticipantKey:
    """Move a linked key to another participant (Admin only, reason required); its Studies follow."""
    key = _visible_key(user, key_id)
    _require_admin_with_reason(user, key, reason)
    participant = _resolve_participant(
        user, key, participant_id, person_source_value, reveal_reason, request, purpose="repoint")
    with transaction.atomic():
        key = _locked_key(key_id)
        if key.study_participant_id is None:
            raise InvalidKeyAction("the key is not linked; link it instead")
        old_participant_id = key.study_participant_id
        if old_participant_id == participant.pk:
            raise InvalidKeyAction("the key is already linked to that participant")
        _set_link(key, participant)
        _audit(
            EVENT_TYPE_PARTICIPANT_KEY_REPOINTED, user, request, key, old_participant_id=str(old_participant_id),
            new_participant_id=str(participant.pk), reason=reason.strip())
    return key


def unlink_key(*, user, key_id, reason, request=None) -> ParticipantKey:
    """Return a linked key (and its Studies) to the admin-only unlinked state (Admin only, reason required)."""
    key = _visible_key(user, key_id)
    _require_admin_with_reason(user, key, reason)
    with transaction.atomic():
        key = _locked_key(key_id)
        if key.study_participant_id is None:
            raise InvalidKeyAction("the key is not linked")
        old_participant_id = key.study_participant_id
        key.study_participant = None
        key.linked_via = ""
        key.linked_job = None
        key.linked_at = None
        key.save(update_fields=["study_participant", "linked_via", "linked_job", "linked_at"])
        _audit(
            EVENT_TYPE_PARTICIPANT_KEY_UNLINKED, user, request, key,
            old_participant_id=str(old_participant_id), reason=reason.strip())
    return key


def _visible_key(user, key_id) -> ParticipantKey:
    """The key. Anyone without a role on its project (or an unknown key) gets NotFound."""
    key = key_with_role(user, key_id)
    if key is None:
        raise NotFound()
    return key


def _locked_key(key_id) -> ParticipantKey:
    key = ParticipantKey.objects.select_for_update(of=("self",)).select_related("project").filter(pk=key_id).first()
    if key is None:
        raise NotFound()
    return key


def _require_admin_with_reason(user, key: ParticipantKey, reason) -> None:
    if not is_project_admin(user, key.project):
        raise NotAllowed("only a project Admin may re-point or unlink Participant Keys")
    if not reason or not reason.strip():
        raise InvalidKeyAction("a reason is required")
    if len(reason.strip()) > MAX_REASON_LENGTH:
        raise InvalidKeyAction(f"the reason may be at most {MAX_REASON_LENGTH} characters")


def _resolve_participant(user, key, participant_id, person_source_value, reveal_reason, request, *, purpose):
    """The participant (of the key's project, within the caller's Participant Visibility) from exactly one of
    `participant_id` and `person_source_value`. The PID path is an audited Identity Reveal."""
    if (participant_id is None) == (not person_source_value):
        raise InvalidKeyAction("give exactly one of participant_id and person_source_value")
    visible = visible_participants(user, key.project)
    if participant_id is not None:
        participant = visible.filter(pk=participant_id).first()
    else:
        if reveal_reason not in REVEAL_REASONS:
            raise InvalidKeyAction("a valid reason is required to look a participant up by identifier")
        participant = visible.filter(
            person_source_value_hash=get_deterministic_hash(format_person_source_value(person_source_value))
        ).first()
        _audit(
            EVENT_TYPE_PID_VIEW, user, request, key, project_id=str(key.project_id),
            purpose=f"participant_key_{purpose}", reason=reveal_reason,
            participant_id=str(participant.pk) if participant else None)
    if participant is None:
        raise InvalidKeyAction("unknown participant")
    return participant


def _set_link(key: ParticipantKey, participant: StudyParticipant) -> None:
    key.study_participant = participant
    key.linked_via = LINK_VIA_ADMIN
    key.linked_job = None
    key.linked_at = timezone.now()
    key.save(update_fields=["study_participant", "linked_via", "linked_job", "linked_at"])

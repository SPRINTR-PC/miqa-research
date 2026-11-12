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
import logging

import pydicom
from django.db import transaction
from django.utils import timezone

from contract.constants.audit_log import (
    EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED,
    EVENT_TYPE_PARTICIPANT_KEY_LINKED,
    EVENT_TYPE_PARTICIPANT_KEY_REPOINTED,
    EVENT_TYPE_PARTICIPANT_KEY_UNLINKED,
    EVENT_TYPE_PID_VIEW,
)
from contract.constants.participant_key import LINK_VIA_ADMIN, REVEAL_REASON_CHOICES
from helpers.db_fields import get_deterministic_hash
from helpers.person_source_value import format_person_source_value
from MiqaResearch.actions.viewer_exceptions import NotAllowed, NotFound, ViewerActionError
from MiqaResearch.data.models import AuditLog, DicomFile, ParticipantKey, StudyParticipant
from MiqaResearch.readers.participant_keys import is_project_admin
from MiqaResearch.readers.participant_visibility import can_open_unlinked, visible_participants

logger = logging.getLogger("mires")

MAX_REASON_LENGTH = 500
_SEX_TO_GENDER = {"M": "M", "F": "F"}


def _birth_date_parts(value: str) -> tuple[int | None, int | None, int | None]:
    """Split a DICOM DA date (YYYYMMDD, possibly partial) into year/month/day.

    A zero component means "unknown" in DICOM and yields None.
    """
    value = value.strip()
    if len(value) < 4 or not value.isdigit():
        return None, None, None
    year = int(value[0:4])
    month = int(value[4:6]) if len(value) >= 6 and value[4:6] != "00" else None
    day = int(value[6:8]) if month is not None and len(value) >= 8 and value[6:8] != "00" else None
    return year, month, day
_REVEAL_REASONS = {value for value, _ in REVEAL_REASON_CHOICES}


class InvalidKeyAction(ViewerActionError):
    """Bad input: unknown participant, missing reason, key in the wrong state. 400 with the message."""


def link_key(
    *, user, key_id, participant_id=None, person_source_value=None, reveal_reason=None,
    fill_demographics=False, request=None,
) -> dict:
    """Link an unlinked key. Linking again to the same participant is a no-op (`changed` False); another one
    is refused (re-point instead). Returns {"key", "changed", "demographics": {"filled": [...], "mismatched": [...]}}.

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
            return {"key": key, "changed": False, "demographics": {"filled": [], "mismatched": []}}
        if key.study_participant_id is not None:
            raise InvalidKeyAction("the key is already linked to another participant; re-point it")
        _set_link(key, participant)
        AuditLog.objects.record(
            EVENT_TYPE_PARTICIPANT_KEY_LINKED, user=user, request=request, project=key.project,
            metadata={
                "key_id": str(key.pk), "participant_id": str(participant.pk),
                "fill_demographics": bool(fill_demographics)},
        )
        demographics = {"filled": [], "mismatched": []}
        if fill_demographics:
            demographics = _fill_demographics(user, key, participant, request)
    return {"key": key, "changed": True, "demographics": demographics}


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
        AuditLog.objects.record(
            EVENT_TYPE_PARTICIPANT_KEY_REPOINTED, user=user, request=request, project=key.project,
            metadata={
                "key_id": str(key.pk), "old_participant_id": str(old_participant_id),
                "new_participant_id": str(participant.pk), "reason": reason.strip()},
        )
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
        AuditLog.objects.record(
            EVENT_TYPE_PARTICIPANT_KEY_UNLINKED, user=user, request=request, project=key.project,
            metadata={"key_id": str(key.pk), "old_participant_id": str(old_participant_id), "reason": reason.strip()},
        )
    return key


def _visible_key(user, key_id) -> ParticipantKey:
    """The key. Anyone without a role on its project (or an unknown key) gets NotFound."""
    key = ParticipantKey.objects.select_related("project").filter(pk=key_id).first()
    if key is None:
        raise NotFound()
    if not (user.is_superuser or key.project.researchprojectuserrolemap_set.filter(user=user).exists()):
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
        if reveal_reason not in _REVEAL_REASONS:
            raise InvalidKeyAction("a valid reason is required to look a participant up by identifier")
        participant = visible.filter(
            person_source_value_hash=get_deterministic_hash(format_person_source_value(person_source_value))
        ).first()
        AuditLog.objects.record(
            EVENT_TYPE_PID_VIEW, user=user, request=request, project=key.project,
            metadata={
                "project_id": str(key.project_id), "purpose": f"participant_key_{purpose}",
                "key_id": str(key.pk), "reason": reveal_reason,
                "participant_id": str(participant.pk) if participant else None},
        )
    if participant is None:
        raise InvalidKeyAction("unknown participant")
    return participant


def _set_link(key: ParticipantKey, participant: StudyParticipant) -> None:
    key.study_participant = participant
    key.linked_via = LINK_VIA_ADMIN
    key.linked_job = None
    key.linked_at = timezone.now()
    key.save(update_fields=["study_participant", "linked_via", "linked_job", "linked_at"])


def _fill_demographics(user, key: ParticipantKey, participant: StudyParticipant, request) -> dict:
    """Fill the participant's blank date of birth and sex (never overwrite) from the key's stored original files;
    report differences. Values never reach the audit log, only which fields were filled."""
    observed = _observed_demographics(key)
    filled, mismatched = [], []
    update_fields = []
    year, month, day = _birth_date_parts(observed.get("birth_date", ""))
    stored = (participant.year_of_birth, participant.month_of_birth, participant.day_of_birth)
    if year is not None:
        if stored == (None, None, None):
            participant.year_of_birth, participant.month_of_birth, participant.day_of_birth = year, month, day
            update_fields += ["year_of_birth", "month_of_birth", "day_of_birth"]
            filled.append("date_of_birth")
        elif stored != (year, month, day):
            mismatched.append("date_of_birth")
    gender = _SEX_TO_GENDER.get(observed.get("sex", ""))
    if gender is not None:
        if participant.gender == "U":
            participant.gender = gender
            update_fields.append("gender")
            filled.append("sex")
        elif participant.gender != gender:
            mismatched.append("sex")
    if update_fields:
        participant.save(update_fields=update_fields)
        AuditLog.objects.record(
            EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED, user=user, request=request, project=key.project,
            metadata={"key_id": str(key.pk), "participant_id": str(participant.pk), "fields": filled},
        )
    return {"filled": filled, "mismatched": mismatched}


def _observed_demographics(key: ParticipantKey) -> dict:
    """Birth date and sex from the first readable stored original of the key's Studies (the metadata dump has
    the birth date blanked by the De-identification Profile)."""
    files = DicomFile.objects.filter(series__study__participant_key=key).order_by("pk")
    for dicom_file in files.iterator():
        try:
            with dicom_file.file.open("rb") as handle:
                ds = pydicom.dcmread(
                    handle, stop_before_pixels=True, specific_tags=["PatientBirthDate", "PatientSex"], force=True)
        except Exception:
            logger.warning("Could not read stored DICOM file %s for demographics", dicom_file.pk, exc_info=True)
            continue
        return {
            "birth_date": str(ds.get("PatientBirthDate") or "").strip(),
            "sex": str(ds.get("PatientSex") or "").strip().upper(),
        }
    return {}

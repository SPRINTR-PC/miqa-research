"""Participant Key matching and linking (ADR 0035, #400).

`link_study_keys` takes the identifiers observed on every instance of one DICOM Study and returns the
Study's Participant Key. Every observed identifier becomes a key; when the Study resolves to a Study
Participant, all its keys are linked to it. It never creates a Study Participant.

Resolution per instance, first step with a hit wins: configured tag vs `alias1`, PatientID vs `alias1`,
PatientID vs `person_source_value` (opt-in, dash-stripped). Keys already linked also resolve an instance.
More than one candidate, an instance resolving differently from another, or a key already linked to a
different participant is an error; nothing is linked (the whole call is one transaction).
"""
from django.db import transaction
from django.utils import timezone

from contract.constants.participant_key import (
    DICOM_KEY_TAG_ALLOWLIST,
    DICOM_PATIENT_ID_KEY_TYPE,
    LINK_VIA_MATCH,
    dicom_key_type,
)
from helpers.db_fields import get_deterministic_hash
from helpers.person_source_value import format_person_source_value
from MiqaResearch.data.models import ParticipantKey, StudyParticipant

PATIENT_ID = "PatientID"


class ParticipantKeyError(Exception):
    pass


class AmbiguousParticipantMatch(ParticipantKeyError):
    """More than one Study Participant matched one identifier step."""


class ParticipantKeyConflict(ParticipantKeyError):
    """The observed identifiers resolve to different Study Participants."""


def link_study_keys(
    project,
    instances: list[dict],
    *,
    configured_tag: str | None = None,
    match_person_source_value: bool = False,
    job=None,
) -> ParticipantKey:
    """The Participant Key of a Study whose instances carry `instances` (keyword -> str or list of str,
    only allow-listed tags are read). Raises ValueError for a bad `configured_tag` or no identifier at
    all, `AmbiguousParticipantMatch` / `ParticipantKeyConflict` otherwise."""
    if configured_tag is not None and configured_tag not in DICOM_KEY_TAG_ALLOWLIST:
        raise ValueError(f"{configured_tag!r} is not an allowed Participant Key tag")
    observed = [_observed(instance) for instance in instances]
    study_key_type, study_value = _study_key(observed, configured_tag)

    with transaction.atomic():
        resolutions = {
            _resolve(project, values, configured_tag, match_person_source_value) for values in observed
        }
        if len(resolutions) > 1:
            raise ParticipantKeyConflict("instances of one Study resolve to different participants")
        (participant,) = resolutions
        keys = {
            (key_type, value): _get_or_create_key(project, key_type, value, job)
            for values in observed
            for key_type, value in values
        }
        if participant is not None:
            for key in keys.values():
                if key.study_participant_id not in (None, participant.pk):
                    raise ParticipantKeyConflict("an observed key is already linked to another participant")
            _link(keys.values(), participant, job)
        return keys[(study_key_type, study_value)]


def _observed(instance: dict) -> list[tuple[str, str]]:
    """The instance's allow-listed identifiers as ordered, de-duplicated (key_type, trimmed value) pairs."""
    pairs = []
    for keyword in DICOM_KEY_TAG_ALLOWLIST:
        raw = instance.get(keyword)
        values = raw if isinstance(raw, list | tuple) else [raw]
        for value in values:
            value = str(value).strip() if value is not None else ""
            if value and (pair := (dicom_key_type(keyword), value)) not in pairs:
                pairs.append(pair)
    return pairs


def _study_key(observed: list[list[tuple[str, str]]], configured_tag: str | None) -> tuple[str, str]:
    """The Study's key: the first configured tag present, else PatientID."""
    for key_type in [dicom_key_type(configured_tag)] if configured_tag else []:
        for values in observed:
            for found_type, value in values:
                if found_type == key_type:
                    return found_type, value
    for values in observed:
        for found_type, value in values:
            if found_type == DICOM_PATIENT_ID_KEY_TYPE:
                return found_type, value
    raise ValueError("no usable identifier (configured tag and PatientID missing or empty)")


def _resolve(project, values: list[tuple[str, str]], configured_tag, match_person_source_value):
    """The one participant this instance's identifiers point to, or None."""
    by_type: dict[str, list[str]] = {}
    for key_type, value in values:
        by_type.setdefault(key_type, []).append(value)
    steps = []
    if configured_tag:
        steps.append(("alias1", by_type.get(dicom_key_type(configured_tag), [])))
    steps.append(("alias1", by_type.get(DICOM_PATIENT_ID_KEY_TYPE, [])))
    if match_person_source_value:
        steps.append(("psv", [format_person_source_value(v) for v in by_type.get(DICOM_PATIENT_ID_KEY_TYPE, [])]))
    for kind, candidates in steps:
        found = _participants(project, kind, candidates)
        if len(found) > 1:
            raise AmbiguousParticipantMatch(f"{len(found)} participants match one identifier")
        if found:
            return found[0]
    linked = {
        key.study_participant_id: key.study_participant
        for key in _existing_keys(project, values).select_related("study_participant")
        if key.study_participant_id
    }
    if len(linked) > 1:
        raise ParticipantKeyConflict("observed keys are linked to different participants")
    return next(iter(linked.values()), None)


def _participants(project, kind: str, candidates: list[str]) -> list[StudyParticipant]:
    if not candidates:
        return []
    participants = StudyParticipant.objects.filter(research_project=project)
    if kind == "alias1":
        return list(participants.filter(alias1__in=candidates))
    hashes = [get_deterministic_hash(value) for value in candidates]
    return list(participants.filter(person_source_value_hash__in=hashes))


def _existing_keys(project, values: list[tuple[str, str]]):
    hashes = {get_deterministic_hash(value) for _, value in values}
    keys = ParticipantKey.objects.filter(project=project, value_hash__in=hashes)
    wanted = set(values)
    return keys.filter(pk__in=[k.pk for k in keys if (k.key_type, k.value) in wanted])


def _get_or_create_key(project, key_type: str, value: str, job) -> ParticipantKey:
    key = ParticipantKey.objects.filter(
        project=project, key_type=key_type, value_hash=get_deterministic_hash(value)
    ).first()
    return key or ParticipantKey.objects.create(project=project, key_type=key_type, value=value, first_seen_job=job)


def _link(keys, participant: StudyParticipant, job) -> None:
    for key in keys:
        if key.study_participant_id is None:
            key.study_participant = participant
            key.linked_via = LINK_VIA_MATCH
            key.linked_job = job
            key.linked_at = timezone.now()
            key.save(update_fields=["study_participant", "linked_via", "linked_job", "linked_at"])


def ensure_linked_key(project, key_type: str, value: str, participant: StudyParticipant, job=None) -> ParticipantKey:
    """The key of `value`, linked to `participant` (for paths that already know the participant, e.g. the
    pre-Datatype ingestion task). Raises `ParticipantKeyConflict` if it is linked to another one."""
    with transaction.atomic():
        key = _get_or_create_key(project, key_type, value.strip(), job)
        if key.study_participant_id not in (None, participant.pk):
            raise ParticipantKeyConflict("the key is already linked to another participant")
        _link([key], participant, job)
        return key

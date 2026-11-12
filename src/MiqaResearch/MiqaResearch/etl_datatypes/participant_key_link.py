"""The `participant_key_link` ETL Datatype (#421, ADR 0035): Participant Key -> Study Participant mapping.

A missing key is created already linked, so a mapping may arrive before the images. All-or-nothing per
Job: the same participant is a no-op, a different one fails the Job; re-pointing is never done here (it is
an explicit Admin action). The Job log and audit metadata carry row numbers and counts only -- never a key
value or a participant identity (the reference-resolution errors, which quote the reference, are replaced).
`fill_demographics` (Binding config, default off) fills blank DOB/sex from the stored original headers.
"""
from contract.constants.audit_log import (
    EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED,
    EVENT_TYPE_PARTICIPANT_KEY_LINKED,
)
from MiqaResearch.actions.participant_demographics import fill_demographics
from MiqaResearch.actions.participant_keys import ParticipantKeyMappingConflict, link_keys_from_mapping
from MiqaResearch.data.models import AuditLog, ResearchProject
from mires_etl.schemas.participant_key_link import ParticipantKeyLinkRowSchema

from .exceptions import AmbiguousParticipantReference, EtlRowError, UnresolvableParticipantReference
from .participant_reference import resolve_participant
from .registry import LoadResult, register_loader


@register_loader("participant_key_link")
def load_participant_key_link_rows(
        *, project: ResearchProject, etl_job, rows: list[ParticipantKeyLinkRowSchema], inputs=None) -> LoadResult:
    mappings = _resolve_rows(project, rows)
    try:
        outcome = link_keys_from_mapping(
            project, [(row.key_type, row.key_value, participant) for row, participant in mappings], job=etl_job)
    except ParticipantKeyMappingConflict as exc:
        raise EtlRowError(f"Key link conflict: {exc}; re-pointing a key is not done through this Datatype.") from None

    AuditLog.objects.record(
        EVENT_TYPE_PARTICIPANT_KEY_LINKED, project=project,
        metadata={"etl_job_id": str(etl_job.id), "created": outcome.created, "linked": outcome.linked,
                  "unchanged": outcome.unchanged})
    if (etl_job.config_snapshot or {}).get("fill_demographics"):
        _fill_demographics(project, etl_job, mappings, outcome.keys)
    return LoadResult(created=outcome.created, updated=outcome.linked)


def _resolve_rows(project, rows):
    mappings, unresolved, ambiguous = [], [], []
    for number, row in enumerate(rows, start=1):
        try:
            mappings.append((row, resolve_participant(project, row)))
        except UnresolvableParticipantReference:
            unresolved.append(number)
        except AmbiguousParticipantReference:
            ambiguous.append(number)
    if unresolved or ambiguous:
        parts = []
        if unresolved:
            parts.append(f"no Study Participant matches the reference on row {_numbers(unresolved)}")
        if ambiguous:
            parts.append(f"more than one Study Participant matches the reference on row {_numbers(ambiguous)}")
        raise EtlRowError("; ".join(parts))
    return mappings


def _numbers(numbers: list[int]) -> str:
    return ", ".join(map(str, numbers))


def _fill_demographics(project, etl_job, mappings, keys) -> None:
    keys_by_participant: dict = {}
    for (row, participant), key in zip(_first_per_key(mappings), keys, strict=True):
        keys_by_participant.setdefault(participant.pk, (participant, []))[1].append(key)
    filled = sum(fill_demographics(participant, keys) for participant, keys in keys_by_participant.values())
    if filled:
        AuditLog.objects.record(
            EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED, project=project,
            metadata={"etl_job_id": str(etl_job.id), "participants": filled})


def _first_per_key(mappings):
    """The mapping rows de-duplicated by key, in the order `link_keys_from_mapping` returns its keys."""
    seen = {}
    for row, participant in mappings:
        seen.setdefault((row.key_type, row.key_value), (row, participant))
    return list(seen.values())

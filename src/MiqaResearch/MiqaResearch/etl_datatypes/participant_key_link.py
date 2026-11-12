"""The `participant_key_link` ETL Datatype (#421, ADR 0035): Participant Key -> Study Participant mapping.

A missing key is created already linked, so a mapping may arrive before the images. All-or-nothing per
Job: the same participant is a no-op, a different one fails the Job; re-pointing is never done here (it is
an explicit Admin action). The Job log and audit metadata carry row numbers and counts only -- never a key
value or a participant identity (the reference-resolution errors, which quote the reference, are replaced).
`fill_demographics` (Binding config, default off) fills blank DOB/sex from the stored original headers.
"""
from MiqaResearch.actions.participant_keys import (
    ParticipantKeyMappingConflict,
    fill_mapped_demographics,
    link_keys_from_mapping,
)
from MiqaResearch.data.models import ResearchProject
from mires_etl.schemas.participant_key_link import ParticipantKeyLinkRowSchema

from .exceptions import AmbiguousParticipantReference, EtlRowError, UnresolvableParticipantReference
from .participant_reference import resolve_participant
from .registry import LoadResult, register_loader


@register_loader("participant_key_link")
def load_participant_key_link_rows(
        *, project: ResearchProject, etl_job, rows: list[ParticipantKeyLinkRowSchema], inputs=None) -> LoadResult:
    mappings = [(row.key_type, row.key_value, participant) for row, participant in _resolve_rows(project, rows)]
    try:
        outcome = link_keys_from_mapping(project, mappings, job=etl_job)
    except ParticipantKeyMappingConflict as exc:
        raise EtlRowError(f"Key link conflict: {exc}; re-pointing a key is not done through this Datatype.") from None

    if (etl_job.config_snapshot or {}).get("fill_demographics"):
        fill_mapped_demographics(project, mappings, outcome.keys, job=etl_job)
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

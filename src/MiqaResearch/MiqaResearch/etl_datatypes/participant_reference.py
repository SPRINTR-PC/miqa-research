"""Participant Reference resolution for ETL Datatype rows (#159).

Every row a Script emits carries a Participant Reference -- `person_source_value` or `alias1`
-- resolved against this project's Study Participants only, never across projects. A reference
that matches more than one participant is a hard error for the whole Job rather than a silent
pick (spec #140, story 18): source systems don't guarantee `person_source_value` is unique, only
`alias1` is (enforced at the DB level), so ambiguity here is a real, expected failure mode.
"""
from helpers.db_fields import get_deterministic_hash
from helpers.person_source_value import format_person_source_value
from MiqaResearch.data.models import ResearchProject, StudyParticipant
from mires_etl.schemas import ParticipantReferenceFields

from .exceptions import AmbiguousParticipantReference, UnresolvableParticipantReference


def resolve_participant(project: ResearchProject, reference: ParticipantReferenceFields) -> StudyParticipant:
    if reference.alias1:
        queryset = StudyParticipant.objects.filter(research_project=project, alias1=reference.alias1)
    else:
        hashed = get_deterministic_hash(format_person_source_value(reference.person_source_value))
        queryset = StudyParticipant.objects.filter(research_project=project, person_source_value_hash=hashed)

    matches = list(queryset[:2])
    if not matches:
        raise UnresolvableParticipantReference(
            f"No Study Participant in this project matches reference {reference!r}.")
    if len(matches) > 1:
        raise AmbiguousParticipantReference(
            f"Reference {reference!r} matches more than one Study Participant in this project.")
    return matches[0]

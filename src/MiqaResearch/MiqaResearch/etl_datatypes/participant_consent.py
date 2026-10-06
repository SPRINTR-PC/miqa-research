"""`participant_consent` ETL Datatype (#226): natural-key upsert into ParticipantConsent.

One row per (participant, consent type, signed date) -- the model's own unique key -- so a
re-imported export updates status and revocation in place rather than duplicating or, as the
legacy SamtyckenUmu task's insert-only path did, silently keeping a stale consent.

Two deliberate departures from the `measurement` pattern, both because consent is how a
participant enters a study:
- An unknown `person_source_value` creates the Study Participant in the Binding's project (with a
  generated alias1) instead of failing the Job. Rows must therefore carry `person_source_value`.
- Consent types are resolved by label within the project and created there when missing.
"""
from datetime import datetime

from ninja import Schema

from helpers.db_fields import get_deterministic_hash
from helpers.person_source_value import format_person_source_value
from helpers.study_participant_alias import generate_study_participant_alias1
from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    StudyParticipant,
)

from .exceptions import AmbiguousParticipantReference
from .registry import LoadResult, register_datatype


class ParticipantConsentRowSchema(Schema):
    person_source_value: str
    name: str | None = None
    consent_type: str
    consent_signed_date: datetime
    status: str | None = None
    consent_revoked_date: datetime | None = None
    clinic_code: str
    participant_information_version: str | None = None
    source: str | None = None


@register_datatype("participant_consent", ParticipantConsentRowSchema)
def load_participant_consent_rows(
        *, project: ResearchProject, etl_job, rows: list[ParticipantConsentRowSchema]) -> LoadResult:
    created = updated = 0
    for row in rows:
        participant = _get_or_create_participant(project, row)
        consent_type, _ = ParticipantConsentType.objects.get_or_create(
            label=row.consent_type, research_project=project)
        clinic, _ = Clinic.objects.get_or_create(
            clinic_code=row.clinic_code, defaults={"clinic_name": row.clinic_code[:60]})
        _, was_created = ParticipantConsent.objects.update_or_create(
            study_participant=participant,
            consent_type=consent_type,
            consent_signed_date=row.consent_signed_date,
            defaults={
                "status": row.status,
                "consent_revoked_date": row.consent_revoked_date,
                "clinic": clinic,
                "participant_information_version": row.participant_information_version,
                "source": row.source,
            },
        )
        created += was_created
        updated += not was_created
    return LoadResult(created=created, updated=updated)


def _get_or_create_participant(project: ResearchProject, row: ParticipantConsentRowSchema) -> StudyParticipant:
    person_source_value = format_person_source_value(row.person_source_value)
    hashed = get_deterministic_hash(person_source_value)
    matches = list(StudyParticipant.objects.filter(research_project=project, person_source_value_hash=hashed)[:2])
    if len(matches) > 1:
        raise AmbiguousParticipantReference(
            "A person_source_value matches more than one Study Participant in this project.")
    if matches:
        return matches[0]
    return StudyParticipant.objects.create(
        research_project=project, person_source_value=person_source_value, name=row.name,
        alias1=generate_study_participant_alias1())

"""`visit_occurrence` ETL Datatype (#159): natural-key upsert into VisitOccurrence, OMOP CDM v5.4.

Natural key: (person, visit_concept, visit_start_date, visit_source_value) -- the same
loader-level contract as `measurement` (see `measurement.py`), scoped to what a source system
reliably repeats across re-exports of the same visit.
"""
from datetime import date, datetime
from uuid import UUID

from MiqaResearch.data.models import ResearchProject, VisitOccurrence

from .concepts import require_existing_concepts
from .participant_reference import ParticipantReferenceFields, resolve_participant
from .registry import LoadResult, register_datatype


class VisitOccurrenceRowSchema(ParticipantReferenceFields):
    visit_concept_id: UUID
    visit_start_date: date
    visit_end_date: date
    visit_source_value: str
    visit_start_datetime: datetime | None = None
    visit_end_datetime: datetime | None = None
    visit_type_concept_id: UUID | None = None
    visit_source_concept_id: UUID | None = None
    admitted_from_concept_id: UUID | None = None
    admitted_from_source_value: str | None = None
    discharged_to_concept_id: UUID | None = None
    discharged_to_source_value: str | None = None


@register_datatype("visit_occurrence", VisitOccurrenceRowSchema)
def load_visit_occurrence_rows(
        *, project: ResearchProject, etl_job, rows: list[VisitOccurrenceRowSchema]) -> LoadResult:
    require_existing_concepts({
        concept_id
        for row in rows
        for concept_id in (
            row.visit_concept_id, row.visit_type_concept_id, row.visit_source_concept_id,
            row.admitted_from_concept_id, row.discharged_to_concept_id,
        )
    })

    created = updated = 0
    for row in rows:
        participant = resolve_participant(project, row)
        _, was_created = VisitOccurrence.objects.update_or_create(
            person=participant,
            visit_concept_id=row.visit_concept_id,
            visit_start_date=row.visit_start_date,
            visit_source_value=row.visit_source_value,
            defaults={
                "visit_end_date": row.visit_end_date,
                "visit_start_datetime": row.visit_start_datetime,
                "visit_end_datetime": row.visit_end_datetime,
                "visit_type_concept_id": row.visit_type_concept_id,
                "visit_source_concept_id": row.visit_source_concept_id,
                "admitted_from_concept_id": row.admitted_from_concept_id,
                "admitted_from_source_value": row.admitted_from_source_value,
                "discharged_to_concept_id": row.discharged_to_concept_id,
                "discharged_to_source_value": row.discharged_to_source_value,
                "etl_job": etl_job,
            },
        )
        created += was_created
        updated += not was_created
    return LoadResult(created=created, updated=updated)

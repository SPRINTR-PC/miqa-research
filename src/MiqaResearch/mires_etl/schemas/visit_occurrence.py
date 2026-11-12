"""`visit_occurrence` Datatype row schema (#159)."""
from datetime import date, datetime
from uuid import UUID

from .participant_reference import ParticipantReferenceFields
from .registry import register_schema


@register_schema("visit_occurrence")
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

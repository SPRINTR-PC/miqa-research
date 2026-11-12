"""`measurement` Datatype row schema (#159)."""
from datetime import date, datetime
from uuid import UUID

from .participant_reference import ParticipantReferenceFields
from .registry import register_schema


@register_schema("measurement")
class MeasurementRowSchema(ParticipantReferenceFields):
    measurement_concept_id: UUID
    measurement_type_concept_id: UUID
    measurement_date: date
    measurement_source_value: str
    measurement_datetime: datetime | None = None
    operator_concept_id: UUID | None = None
    value_as_number: float | None = None
    value_as_concept_id: UUID | None = None
    unit_concept_id: UUID | None = None
    unit_source_value: str | None = None
    value_source_value: str | None = None
    range_low: float | None = None
    range_high: float | None = None

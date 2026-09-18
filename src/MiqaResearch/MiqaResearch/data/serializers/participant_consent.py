from datetime import date, datetime
from uuid import UUID

from ninja import Schema


class UploadConsentSchema(Schema):
    participant_study_id: str
    status: str
    signed_date: datetime
    last_updated: datetime
    retracted: datetime | None
    clinic: str
    comment: str
    consent_labels: list[str]
    participant_information_version: str | None
    source: str | None
    extra_info: dict[str, list[str]] | None


class ConsentHistoryEventSchema(Schema):
    consent_count: int
    retracted_count: int
    timestamp: datetime


class ConsentListSchema(Schema):
    participant_study_id: UUID | str
    alias: str
    status: str
    signed_date: datetime
    last_updated: datetime
    retracted: datetime | None
    clinic: str
    participant_information_version: str | None
    consent_labels: list[str]
    comment: str
    source: str | None


class ConsentListWithExtraInfoSchema(ConsentListSchema):
    extra_info: dict[str, list[str]] | None


class ClinicConsentHistorySchema(Schema):
    clinic_id: UUID | str
    clinic_name: str
    consent_history: list[ConsentHistoryEventSchema]

class ProjectConsentHistoryByClinicSchema(Schema):
    project_id: str | UUID
    consent_data_by_clinic: list[ClinicConsentHistorySchema]

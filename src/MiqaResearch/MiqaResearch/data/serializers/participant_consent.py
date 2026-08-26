from datetime import date, datetime

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
    extra_info: dict[str, list[str]] | None

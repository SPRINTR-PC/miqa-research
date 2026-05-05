from datetime import date, datetime

from ninja import Schema


class UploadConsentSchema(Schema):
    participant_study_id: str
    status: str
    signed_date: date
    last_updated: datetime
    retracted: date | None
    clinic: str
    research_person_info: str
    comment: str
    consent_labels: list[str]

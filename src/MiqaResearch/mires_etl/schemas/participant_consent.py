"""`participant_consent` Datatype row schema (#226)."""
from datetime import datetime

from pydantic import BaseModel, Field

from .registry import register_schema


@register_schema("participant_consent")
class ParticipantConsentRowSchema(BaseModel):
    person_source_value: str = Field(
        description="The participant's identifier in the source system; matches or creates the Study Participant.",
        examples=["19900101-1234"])
    name: str | None = Field(default=None, description="The participant's name, if the export has one.")
    consent_type: str = Field(
        description="Label of the consent type; created in the project when it does not exist.",
        examples=["Biobank"])
    consent_signed_date: datetime = Field(description="When the consent was signed. Part of the row's unique key.")
    status: str | None = Field(default=None, description="Consent status as given by the source.")
    consent_revoked_date: datetime | None = Field(default=None, description="When the consent was revoked, if it was.")
    clinic_code: str = Field(
        description="Code of the clinic the consent was given at; created when it does not exist.", examples=["UMEA"])
    participant_information_version: str | None = Field(
        default=None, description="Version of the participant information the participant was given.")
    source: str | None = Field(default=None, description="Where this row came from, for provenance.")

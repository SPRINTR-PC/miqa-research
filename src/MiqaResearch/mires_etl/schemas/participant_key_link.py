"""`participant_key_link` Datatype row schema (#421): maps one Participant Key to a Study Participant.

Errors hide their input: key values and participant references are identifying, and a validation
failure ends up in the Job log."""
from pydantic import ConfigDict, Field, field_validator

from .participant_reference import ParticipantReferenceFields
from .registry import register_schema

# Mirrors contract.constants.participant_key.DICOM_KEY_TAG_ALLOWLIST (a test keeps them equal); this
# package is Django-free and ships to the sandbox images without the app.
DICOM_KEY_TAG_ALLOWLIST = (
    "PatientID", "OtherPatientIDs", "PatientName", "IssuerOfPatientID", "AccessionNumber", "StudyID",
)
KEY_TYPE_PREFIX = "dicom:"


@register_schema("participant_key_link")
class ParticipantKeyLinkRowSchema(ParticipantReferenceFields):
    model_config = ConfigDict(hide_input_in_errors=True)

    key_type: str = Field(
        description="Which identifier the key is: `dicom:<tag>` for an allow-listed DICOM tag, or the bare tag.",
        examples=["dicom:PatientID"])
    key_value: str = Field(description="The identifier value as it appears in the images (pseudonym).")

    @field_validator("key_type")
    @classmethod
    def _allow_listed_dicom_tag(cls, value: str) -> str:
        tag = value.strip().removeprefix(KEY_TYPE_PREFIX)
        if tag not in DICOM_KEY_TAG_ALLOWLIST:
            raise ValueError("key_type must be an allow-listed DICOM tag")
        return KEY_TYPE_PREFIX + tag

    @field_validator("key_value")
    @classmethod
    def _trimmed_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("key_value must not be empty")
        return value

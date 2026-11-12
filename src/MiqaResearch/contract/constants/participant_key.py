"""Participant Key types (`<source>:<attribute>`, ADR 0035) and link provenance."""

KEY_SOURCE_DICOM = "dicom"
LEGACY_KEY_TYPE = "legacy:participant"

# DICOM identifier tags a Binding may configure as the Participant Key (keyword -> key_type suffix).
DICOM_KEY_TAG_ALLOWLIST = (
    "PatientID",
    "OtherPatientIDs",
    "PatientName",
    "IssuerOfPatientID",
    "AccessionNumber",
    "StudyID",
)
DICOM_PATIENT_ID_KEY_TYPE = "dicom:PatientID"

LINK_VIA_MATCH = "match"
LINK_VIA_DATATYPE = "datatype"
LINK_VIA_ADMIN = "admin"
LINK_VIA_LEGACY = "legacy"
LINK_VIA_CHOICES = [
    (LINK_VIA_MATCH, "Matched at ingest"),
    (LINK_VIA_DATATYPE, "participant_key_link Datatype"),
    (LINK_VIA_ADMIN, "Admin"),
    (LINK_VIA_LEGACY, "Migrated legacy"),
]


def dicom_key_type(tag_keyword: str) -> str:
    return f"{KEY_SOURCE_DICOM}:{tag_keyword}"

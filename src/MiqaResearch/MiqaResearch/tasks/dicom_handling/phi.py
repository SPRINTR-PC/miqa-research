"""PHI tag definitions for the per-file metadata dump (#114).

Directly-identifying tags that must be removed from `DicomFile.metadata`
before storage, so the unencrypted JSON store can't become an unintended
second copy of PHI. Keyed by DICOM keyword (all entries are public tags);
stripping is applied recursively, so a PHI tag nested inside any sequence is
removed along with it (and a PHI-bearing sequence such as
OtherPatientIDsSequence is removed whole).

Deliberately not stripped: `PatientSex`/`PatientAge` (demographic attributes,
not direct identifiers — they drive participant demographics).
"""

PHI_TAG_KEYWORDS: frozenset[str] = frozenset({
    # Patient identity
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientBirthTime",
    "OtherPatientIDs",
    "OtherPatientNames",
    "OtherPatientIDsSequence",
    "PatientMotherBirthName",
    "PatientTelephoneNumbers",
    "PatientAddress",
    # Treating/referring staff identity
    "ReferringPhysicianName",
    "ReferringPhysicianAddress",
    "ReferringPhysicianTelephoneNumbers",
    "ReferringPhysicianIdentificationSequence",
    "PerformingPhysicianName",
    "PhysiciansOfRecord",
    "OperatorsName",
    "NameOfPhysiciansReadingStudy",
    "ResponsiblePerson",
})

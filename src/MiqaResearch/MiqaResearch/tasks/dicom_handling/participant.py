"""Participant stage: match or create the StudyParticipant for an incoming file (#100).

Matching is scoped to the ingestion run's Research Project (never
cross-project), via the same deterministic hash lookup the consent import
uses. A match never overwrites the participant's demographics; a newly
created participant gets its demographics from the file's tags and a
pseudonymous `alias1` via the existing alias generator.
"""
from pydicom.dataset import Dataset

from helpers.db_fields import get_deterministic_hash
from helpers.study_participant_alias import generate_study_participant_alias1
from MiqaResearch.data.models import ResearchProject, StudyParticipant

_SEX_TO_GENDER = {"M": "M", "F": "F"}


def patient_id_of(ds: Dataset) -> str:
    """The file's PatientID as a clean string ("" when missing/empty)."""
    raw = ds.get("PatientID")
    return str(raw).strip() if raw is not None else ""


def match_or_create_participant(ds: Dataset, research_project: ResearchProject) -> StudyParticipant:
    """Return the project-scoped participant for the file's PatientID, creating one if absent.

    Raises ValueError when the file carries no usable patient identifier —
    such a file is a per-file error, never matched to an anonymous participant (#100).
    """
    patient_id = patient_id_of(ds)
    if not patient_id:
        raise ValueError("file has no usable patient identifier (PatientID missing or empty)")

    participant = (
        StudyParticipant.objects.filter(research_project=research_project)
        .filter(person_source_value_hash=get_deterministic_hash(patient_id))
        .first()
    )
    if participant is not None:
        return participant
    return _create_participant(ds, patient_id, research_project)


def _create_participant(ds: Dataset, patient_id: str, research_project: ResearchProject) -> StudyParticipant:
    name = str(ds.get("PatientName") or "").strip() or None
    year, month, day = _birth_date_parts(str(ds.get("PatientBirthDate") or ""))
    sex = str(ds.get("PatientSex") or "").strip().upper()
    return StudyParticipant.objects.create(
        person_source_value=patient_id,
        name=name,
        alias1=generate_study_participant_alias1(),
        year_of_birth=year,
        month_of_birth=month,
        day_of_birth=day,
        gender=_SEX_TO_GENDER.get(sex, "U"),
        research_project=research_project,
    )


def _birth_date_parts(value: str) -> tuple[int | None, int | None, int | None]:
    """Split a DICOM DA date (YYYYMMDD, possibly partial) into year/month/day.

    A zero component means "unknown" in DICOM and yields None.
    """
    value = value.strip()
    if len(value) < 4 or not value.isdigit():
        return None, None, None
    year = int(value[0:4])
    month = int(value[4:6]) if len(value) >= 6 and value[4:6] != "00" else None
    day = int(value[6:8]) if month is not None and len(value) >= 8 and value[6:8] != "00" else None
    return year, month, day

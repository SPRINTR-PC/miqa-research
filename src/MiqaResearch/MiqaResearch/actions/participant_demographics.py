"""Fill a Study Participant's blank date of birth and sex from the stored original DICOM headers (#400, #421).

Only blanks are filled, never overwritten. Nothing here logs or returns the values read."""
from dataclasses import dataclass, field

from pydicom import dcmread
from pydicom.errors import InvalidDicomError

from MiqaResearch.data.models import ParticipantKey, StudyParticipant
from MiqaResearch.readers.participant_key_originals import open_original_dicom_files

PATIENT_SEX_TO_GENDER = {"M": "M", "F": "F", "O": "O"}
_TAGS = ["PatientBirthDate", "PatientSex"]


@dataclass(frozen=True)
class DemographicsOutcome:
    filled: list[str] = field(default_factory=list)  # "date_of_birth", "sex"
    mismatched: list[str] = field(default_factory=list)  # stored value differs from the originals' (never changed)


def fill_demographics(participant: StudyParticipant, keys: list[ParticipantKey]) -> bool:
    """Fills `participant`'s blank DOB / sex from the first usable value in the originals behind `keys`.
    Returns whether anything was filled. Reads no file when nothing is blank."""
    if participant.year_of_birth is not None and participant.gender != "U":
        return False
    return bool(_fill(participant, keys, compare=False).filled)


def fill_and_compare_demographics(participant: StudyParticipant, keys: list[ParticipantKey]) -> DemographicsOutcome:
    """Like `fill_demographics`, and also reports which already-set values differ from the originals."""
    return _fill(participant, keys, compare=True)


def _fill(participant: StudyParticipant, keys, *, compare: bool) -> DemographicsOutcome:
    need_birth = participant.year_of_birth is None
    need_sex = participant.gender == "U"
    birth = _first_birth(keys) if need_birth or compare else None
    sex = _first_sex(keys) if need_sex or compare else None
    outcome = DemographicsOutcome()
    update_fields = []
    if birth:
        if need_birth:
            participant.year_of_birth, participant.month_of_birth, participant.day_of_birth = birth
            update_fields += ["year_of_birth", "month_of_birth", "day_of_birth"]
            outcome.filled.append("date_of_birth")
        elif birth != (participant.year_of_birth, participant.month_of_birth, participant.day_of_birth):
            outcome.mismatched.append("date_of_birth")
    if sex:
        if need_sex:
            participant.gender = sex
            update_fields.append("gender")
            outcome.filled.append("sex")
        elif participant.gender != sex:
            outcome.mismatched.append("sex")
    if update_fields:
        participant.save(update_fields=update_fields)
    return outcome


def _first_birth(keys):
    for dataset in _datasets(keys):
        if (birth := _parse_birth_date(str(dataset.get("PatientBirthDate", "") or ""))):
            return birth
    return None


def _first_sex(keys):
    for dataset in _datasets(keys):
        if (sex := PATIENT_SEX_TO_GENDER.get(str(dataset.get("PatientSex", "") or "").strip().upper())):
            return sex
    return None


def _datasets(keys):
    for key in keys:
        for handle in open_original_dicom_files(key):
            try:
                yield dcmread(handle, stop_before_pixels=True, specific_tags=_TAGS, force=True)
            except (InvalidDicomError, OSError, ValueError, EOFError):
                continue


def _parse_birth_date(value: str):
    """(year, month|None, day|None) from DICOM DA `YYYYMMDD`; None unless at least a plausible year."""
    value = value.strip()
    if len(value) < 4 or not value[:4].isdigit() or int(value[:4]) < 1800:
        return None
    month = int(value[4:6]) if len(value) >= 6 and value[4:6].isdigit() and 1 <= int(value[4:6]) <= 12 else None
    day = int(value[6:8]) if month and len(value) >= 8 and value[6:8].isdigit() and 1 <= int(value[6:8]) <= 31 else None
    return int(value[:4]), month, day

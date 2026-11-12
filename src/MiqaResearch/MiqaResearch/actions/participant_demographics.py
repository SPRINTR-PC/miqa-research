"""Fill a Study Participant's blank date of birth and sex from the stored original DICOM headers (#400, #421).

Only blanks are filled, never overwritten. Nothing here logs or returns the values read."""
from pydicom import dcmread
from pydicom.errors import InvalidDicomError

from MiqaResearch.data.models import ParticipantKey, StudyParticipant
from MiqaResearch.readers.participant_key_originals import open_original_dicom_files

PATIENT_SEX_TO_GENDER = {"M": "M", "F": "F", "O": "O"}
_TAGS = ["PatientBirthDate", "PatientSex"]


def fill_demographics(participant: StudyParticipant, keys: list[ParticipantKey]) -> bool:
    """Fills `participant`'s blank DOB / sex from the first usable value in the originals behind `keys`.
    Returns whether anything was filled."""
    need_birth = participant.year_of_birth is None
    need_sex = participant.gender == "U"
    if not (need_birth or need_sex):
        return False
    birth = _first_birth(keys) if need_birth else None
    sex = _first_sex(keys) if need_sex else None
    update_fields = []
    if birth:
        participant.year_of_birth, participant.month_of_birth, participant.day_of_birth = birth
        update_fields += ["year_of_birth", "month_of_birth", "day_of_birth"]
    if sex:
        participant.gender = sex
        update_fields.append("gender")
    if update_fields:
        participant.save(update_fields=update_fields)
    return bool(update_fields)


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

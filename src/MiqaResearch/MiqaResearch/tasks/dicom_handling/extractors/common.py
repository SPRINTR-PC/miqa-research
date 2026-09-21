"""Fields common to all extraction handlers (not modality-specific)."""
from datetime import UTC, datetime

from pydicom.dataset import Dataset

from helpers.dicom_uid import pseudonymize_uid


def common_extraction(ds: Dataset) -> dict:
    return {
        "study_datetime": _study_datetime(ds),
        "study_description": _clean_str(ds.get("StudyDescription")),
        "series_description": _clean_str(ds.get("SeriesDescription")),
        "modality": _clean_str(ds.get("Modality")),
        "contains_burned_in_annotations": _burned_in_annotation(ds.get("BurnedInAnnotation")),
    }


def _clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _burned_in_annotation(value) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ("M", "Y"):
        return True
    if text == "N":
        return False
    return None


def _study_datetime(ds: Dataset) -> datetime:
    """The study's start datetime from StudyDate/StudyTime, UTC-assumed.

    Falls back to "now" when the file carries no usable StudyDate —
    `DicomStudy.study_datetime` is non-nullable.
    """
    date = str(ds.get("StudyDate") or "").strip()
    time = str(ds.get("StudyTime") or "").strip()
    if date.isdigit() and len(date) == 8:
        try:
            result = datetime.strptime(date, "%Y%m%d")
            if time:
                base, _, fraction = time.partition(".")
                microsecond = int(f"{fraction}000000"[:6]) if fraction else 0
                result = result.replace(
                    hour=int(base[0:2]),
                    minute=int(base[2:4]),
                    second=int(base[4:6]),
                    microsecond=microsecond,
                )
            return result.replace(tzinfo=UTC)
        except (ValueError, IndexError):
            pass
    return datetime.now(UTC)


def image_geometry(ds: Dataset, research_project) -> dict:
    """Image-plane geometry columns from the standard image-plane tags; absent tags give None."""
    # ImageOrientationPatient is a 3-valued DS (row direction cosines), PS3.3 C.7.5.1.1
    for_uid = str(ds.get("FrameOfReferenceUID") or "").strip()
    return {
        "image_orientation_patient": _decimal_list(ds.get("ImageOrientationPatient"), 3),
        "image_position_patient": _decimal_list(ds.get("ImagePositionPatient"), 3),
        "pixel_spacing": _decimal_list(ds.get("PixelSpacing"), 2),
        "frame_of_reference_uid": pseudonymize_uid(for_uid, research_project) if for_uid else None,
    }


def _decimal_list(value, expected_length: int) -> list[float] | None:
    """Convert a DS value (list, or backslash-delimited string) into a float list.

    Returns None when the tag is absent or malformed.
    """
    if value is None:
        return None
    try:
        # Multi-valued DS tags read back as (UserList-based) iterables; single
        # values as str or number. Normalize both to a list of floats.
        parts = value.split("\\") if isinstance(value, str) else [float(item) for item in value]
        numbers = [float(part) for part in parts]
    except (TypeError, ValueError, AttributeError):
        return None
    if len(numbers) != expected_length:
        return None
    return numbers

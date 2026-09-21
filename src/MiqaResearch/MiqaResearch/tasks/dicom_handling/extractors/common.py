"""Fields common to all extraction handlers (not modality-specific)."""
from datetime import UTC, datetime

from pydicom.dataset import Dataset


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

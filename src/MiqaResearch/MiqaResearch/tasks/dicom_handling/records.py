"""Record stage: create-or-match the Study/Series/File hierarchy by pseudonymized UIDs.

Study/Series fields are fill-blank-only: values populate on first creation and
only fill still-blank fields on later matches — a disagreeing later file never
overwrites an earlier value. The series' `file_size_in_mb` aggregate always
accumulates. Matching is by the pseudonymized UID values, never the raw source
ones (#115).
"""
from uuid import uuid7

from django.db.models import F, Sum
from django.db.models.functions import Coalesce

from MiqaResearch.data.models import DicomFile, DicomSeries, DicomStudy, StudyParticipant

# Extraction keys that map 1:1 onto DicomFile geometry/flag columns.
_FILE_COLUMN_KEYS = (
    "image_orientation_patient",
    "image_position_patient",
    "pixel_spacing",
    "frame_of_reference_uid",
    "contains_burned_in_annotations",
)


def build_hierarchy(
    study_participant: StudyParticipant,
    research_project,
    pseudonyms: dict[str, str],
    extracted: dict,
    file_size_in_mb: float,
) -> DicomFile:
    """Create or match Study + Series, and construct (not save) the new DicomFile."""
    study = _upsert_study(
        study_participant,
        pseudonyms["study"],
        {
            "study_datetime": extracted["study_datetime"],
            "study_description": extracted.get("study_description"),
        },
    )
    series = _upsert_series(
        study,
        pseudonyms["series"],
        {
            "series_description": extracted.get("series_description"),
            "modality": extracted.get("modality"),
        },
    )
    return DicomFile(
        id=uuid7(),
        series=series,
        research_project=research_project,
        sop_instance_uid=pseudonyms["sop"],
        metadata=extracted.get("metadata"),
        file_size_in_mb=file_size_in_mb,
        **{key: extracted.get(key) for key in _FILE_COLUMN_KEYS},
    )


def add_file_size_to_series(series: DicomSeries, file_size_in_mb: float) -> None:
    """Accumulate a newly ingested file's size into the series aggregate."""
    DicomSeries.objects.filter(pk=series.pk).update(
        file_size_in_mb=Coalesce(F("file_size_in_mb"), 0.0) + file_size_in_mb
    )


def set_series_file_size(series: DicomSeries) -> None:
    """Resync the series' size aggregate to the current sum of its files' sizes.

    Used after an in-place update, where the file's size contribution changes
    rather than a new file being added.
    """
    total = DicomFile.objects.filter(series=series).aggregate(total=Sum("file_size_in_mb"))["total"]
    DicomSeries.objects.filter(pk=series.pk).update(file_size_in_mb=total or 0.0)


def fill_study_series_blanks(series: DicomSeries, extracted: dict) -> None:
    """Fill still-blank Study/Series fields from `extracted` (never overwrite)."""
    _fill_blanks(
        series.study,
        {
            "study_datetime": extracted["study_datetime"],
            "study_description": extracted.get("study_description"),
        },
    )
    _fill_blanks(
        series,
        {
            "series_description": extracted.get("series_description"),
            "modality": extracted.get("modality"),
        },
    )


def update_file_in_place(dcm_file: DicomFile, extracted: dict, file_size_in_mb: float, content_sha256: str) -> None:
    """Replace an existing DicomFile's file-level data in place (#109 update mode).

    Study/Series fields are handled separately (fill-blank-only); the series'
    size aggregate is resynced so the updated file's new size replaces — never
    adds to — its previous contribution.
    """
    dcm_file.metadata = extracted.get("metadata")
    for key in _FILE_COLUMN_KEYS:
        setattr(dcm_file, key, extracted.get(key))
    dcm_file.file_size_in_mb = file_size_in_mb
    dcm_file.content_sha256 = content_sha256
    dcm_file.save()
    set_series_file_size(dcm_file.series)


def _upsert_study(study_participant: StudyParticipant, study_uid: str, fields: dict) -> DicomStudy:
    study, _ = DicomStudy.objects.get_or_create(
        study_participant=study_participant,
        study_instance_uid=study_uid,
        defaults=fields,
    )
    return _fill_blanks(study, fields)


def _upsert_series(study: DicomStudy, series_uid: str, fields: dict) -> DicomSeries:
    series, _ = DicomSeries.objects.get_or_create(
        study=study,
        series_instance_uid=series_uid,
        defaults=fields,
    )
    return _fill_blanks(series, fields)


def _fill_blanks(instance, fields: dict):
    """Set only still-blank fields from `fields` (never overwrite populated values)."""
    updates = {
        key: value
        for key, value in fields.items()
        if getattr(instance, key) in (None, "") and value not in (None, "")
    }
    if updates:
        for key, value in updates.items():
            setattr(instance, key, value)
        instance.save(update_fields=list(updates))
    return instance

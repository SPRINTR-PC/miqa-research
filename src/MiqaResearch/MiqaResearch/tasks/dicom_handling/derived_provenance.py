"""Provenance for ingested Annotations and Segmentations (ADR 0026, #287).

An SR, ANN, SEG or RTSTRUCT arriving through ingestion is version 1 of its own
chain, with no author. Its source series are the participant's Dicom Series
it references anywhere in its header (SeriesInstanceUID inside any sequence),
matched by pseudonym.
"""
from pydicom.dataset import Dataset
from pydicom.tag import Tag

from contract.constants.annotation import KIND_BY_MODALITY, SOURCE_INGESTED
from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.data.models import DerivedObjectProvenance, DicomFile, DicomSeries

_SERIES_INSTANCE_UID = Tag(0x0020, 0x000E)
_MAX_DEPTH = 16


def record_ingested_provenance(dcm_file: DicomFile, dataset: Dataset, research_project) -> None:
    """Give a newly ingested derived object's series its provenance (once per series)."""
    series = dcm_file.series
    kind = KIND_BY_MODALITY.get((series.modality or "").strip().upper())
    if kind is None:
        return
    provenance, _ = DerivedObjectProvenance.objects.get_or_create(
        series=series, defaults={"kind": kind, "source": SOURCE_INGESTED, "author": None, "version": 1}
    )
    referenced = {pseudonymize_uid(uid, research_project) for uid in _referenced_series_uids(dataset, depth=0)}
    referenced.discard(series.series_instance_uid)
    if not referenced:
        return
    sources = DicomSeries.objects.filter(
        series_instance_uid__in=referenced, study__study_participant_id=series.study.study_participant_id
    )
    provenance.source_series.add(*sources)


def _referenced_series_uids(dataset: Dataset, depth: int):
    for element in dataset:
        if element.VR != "SQ" or depth >= _MAX_DEPTH:
            continue
        for item in element.value or ():
            value = str(item.get(_SERIES_INSTANCE_UID).value or "").strip() if _SERIES_INSTANCE_UID in item else ""
            if value:
                yield value
            yield from _referenced_series_uids(item, depth + 1)

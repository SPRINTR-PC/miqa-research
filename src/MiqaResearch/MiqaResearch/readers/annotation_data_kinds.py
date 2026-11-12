"""Data Kind split of Dicom Series into imaging, Annotations and Segmentations (ADR 0026, #287).

For the sibling Data Kind registry (#175): Dicom Series are split by modality —
SR/ANN are Annotations, SEG/RTSTRUCT are Segmentations, everything else
(including a missing modality) is imaging. For Annotations and Segmentations,
count = chain heads that aren't retired; size = all bytes, every version.
"""
from dataclasses import dataclass

from django.db.models import Q, QuerySet, Sum

from contract.constants.annotation import ANNOTATION_MODALITIES, DERIVED_MODALITIES, SEGMENTATION_MODALITIES
from MiqaResearch.data.models import DicomSeries

DATA_KIND_DICOM_SERIES = "dicom_series"
DATA_KIND_ANNOTATIONS = "annotations"
DATA_KIND_SEGMENTATIONS = "segmentations"

_MODALITIES = {
    DATA_KIND_ANNOTATIONS: ANNOTATION_MODALITIES,
    DATA_KIND_SEGMENTATIONS: SEGMENTATION_MODALITIES,
}


@dataclass(frozen=True)
class DataKindTotals:
    count: int
    size_in_mb: float


def data_kind_for_modality(modality: str | None) -> str:
    """The Data Kind a Dicom Series of `modality` belongs to."""
    normalized = (modality or "").strip().upper()
    for data_kind, modalities in _MODALITIES.items():
        if normalized in modalities:
            return data_kind
    return DATA_KIND_DICOM_SERIES


def series_of_data_kind(data_kind: str, series: QuerySet[DicomSeries] | None = None) -> QuerySet[DicomSeries]:
    """The Dicom Series of `data_kind` among `series` (default: all), every version included."""
    series = DicomSeries.objects.all() if series is None else series
    if data_kind == DATA_KIND_DICOM_SERIES:
        return series.filter(Q(modality__isnull=True) | ~Q(modality__in=DERIVED_MODALITIES))
    return series.filter(modality__in=_MODALITIES[data_kind])


def data_kind_totals(data_kind: str, series: QuerySet[DicomSeries] | None = None) -> DataKindTotals:
    """Count and size of `data_kind` among `series`, e.g.
    `DicomSeries.objects.filter(study__participant_key__study_participant=p)`."""
    of_kind = series_of_data_kind(data_kind, series)
    size = of_kind.aggregate(total=Sum("file_size_in_mb"))["total"] or 0.0
    counted = of_kind
    if data_kind != DATA_KIND_DICOM_SERIES:
        # a series with no provenance yet (ingested before #287) counts as its own head
        counted = of_kind.filter(provenance__successor__isnull=True).exclude(provenance__retired=True)
    return DataKindTotals(count=counted.count(), size_in_mb=size)

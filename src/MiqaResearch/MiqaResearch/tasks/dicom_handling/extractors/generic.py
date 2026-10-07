"""Generic fallback extractor (#110): best-effort capture of the file's tags.

Any SOP Class without a dedicated handler lands here. The tag dump is
de-identified (De-identification Profile, ADR 0028) inside build_metadata_dump itself.
"""
from pydicom.dataset import Dataset

from ..metadata_dump import build_metadata_dump
from .common import common_extraction


def extract(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = common_extraction(ds)
    result["metadata"] = build_metadata_dump(ds, research_project, participant_alias)
    return result

"""Capture a DICOM header's tags into a JSON-safe dict for `DicomFile.metadata`.

Best-effort generic capture (#110). The header (file meta + main dataset) is
first run through the De-identification Profile (`helpers.dicom_deidentification`,
ADR 0028) — the same sanitizer WADO-RS serves through — so the metadata store
never holds PHI or original instance UIDs. Every remaining tag, recursively
inside sequences, is then converted to JSON-safe primitives. Pixel data is
never captured.
"""
import collections.abc

from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset

from helpers.dicom_deidentification import deidentify

# Binary/payload tags never captured into the metadata store.
_SKIPPED_KEYWORDS = frozenset({"PixelData"})

# Sequences nested deeper than this are flattened to a string placeholder —
# best-effort capture must not follow unbounded structure.
_MAX_SEQUENCE_DEPTH = 8


def build_metadata_dump(
    ds: Dataset, research_project, participant_alias: str, *, uids_already_pseudonymized: bool = False
) -> dict:
    """Build the JSON-safe dump of `ds`'s header after de-identifying it.

    `participant_alias` is the Study Participant pseudonym that replaces
    PatientName and PatientID. `uids_already_pseudonymized` is passed to the
    sanitizer for viewer-saved objects (#287), whose UIDs are already pseudonyms.
    """
    sanitized = deidentify(
        ds, research_project=research_project, participant_alias=participant_alias,
        uids_already_pseudonymized=uids_already_pseudonymized,
    )
    dump: dict = {}
    for element in _header_elements(sanitized):
        keyword = _element_key(element)
        if keyword in _SKIPPED_KEYWORDS:
            continue
        dump[keyword] = _to_json_safe(element.value, depth=0)
    return dump


def _header_elements(ds: Dataset):
    file_meta = getattr(ds, "file_meta", None)
    if file_meta:
        yield from file_meta
    yield from ds


def _element_key(element: DataElement) -> str:
    if element.keyword:
        return element.keyword
    tag = element.tag
    return f"{tag.group:04X},{tag.element:04X}"


def _to_json_safe(value, depth: int):
    if depth >= _MAX_SEQUENCE_DEPTH:
        return str(value)
    if isinstance(value, Dataset):
        return {
            _element_key(element): _to_json_safe(element.value, depth + 1)
            for element in value
        }
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, collections.abc.Sequence):
        # covers list, tuple, and pydicom Sequence (an abc.MutableSequence);
        # without this branch a whole sequence would be stringified into one
        # opaque blob
        return [_to_json_safe(item, depth + 1) for item in value]
    return str(value)

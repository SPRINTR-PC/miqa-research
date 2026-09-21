"""Capture a DICOM header's tags into a JSON-safe dict for `DicomFile.metadata`.

Best-effort generic capture (#110): every tag at the top level of the header
(file meta + main dataset) and, recursively, inside sequences is converted to
JSON-safe primitives. Before the dump is returned it is (a) stripped of the
defined PHI tag set (phi.PHI_TAG_KEYWORDS) and (b) rewritten so the
Study/Series/SOP-Instance/Frame-of-Reference UIDs carry their HashUID
pseudonyms (#115) — the metadata store can therefore never contain the
original identifiers. Pixel data is never captured.
"""
import collections.abc

from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset

from helpers.dicom_uid import pseudonymize_uid

from .phi import PHI_TAG_KEYWORDS

# UID keywords that must be pseudonymized at every occurrence they appear in
# the dump (#116 story 27) — including nested sequence items, where each
# original UID gets its own deterministic pseudonym.
PSEUDONYMIZED_UID_KEYWORDS: frozenset[str] = frozenset({
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    # File-meta twin of SOPInstanceUID — same identifier, must be rewritten too.
    "MediaStorageSOPInstanceUID",
    "FrameOfReferenceUID",
})

# Binary/payload tags never captured into the metadata store.
_SKIPPED_KEYWORDS = frozenset({"PixelData"})

# Sequences nested deeper than this are flattened to a string placeholder —
# best-effort capture must not follow unbounded structure.
_MAX_SEQUENCE_DEPTH = 8


def build_metadata_dump(ds: Dataset, research_project) -> dict:
    """Build the PHI-stripped, UID-pseudonymized JSON-safe dump of `ds`'s header."""
    dump: dict = {}
    for element in _header_elements(ds):
        keyword = _element_key(element)
        if keyword in _SKIPPED_KEYWORDS:
            continue
        dump[keyword] = _to_json_safe(element.value, depth=0)
    return _replace_uids(_strip_phi(dump), research_project)


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
        # without this branch a whole sequence (PHI included) would be
        # stringified into one opaque blob
        return [_to_json_safe(item, depth + 1) for item in value]
    return str(value)


def _strip_phi(node):
    if isinstance(node, dict):
        return {k: _strip_phi(v) for k, v in node.items() if k not in PHI_TAG_KEYWORDS}
    if isinstance(node, list):
        return [_strip_phi(item) for item in node]
    return node


def _replace_uids(node, research_project):
    if isinstance(node, dict):
        result = {}
        for keyword, value in node.items():
            if keyword in PSEUDONYMIZED_UID_KEYWORDS:
                result[keyword] = _pseudonymize_uid_value(value, research_project)
            else:
                result[keyword] = _replace_uids(value, research_project)
        return result
    if isinstance(node, list):
        return [_replace_uids(item, research_project) for item in node]
    return node


def _pseudonymize_uid_value(value, research_project):
    """Pseudonymize each original UID value for the project (per value, so
    distinct referenced UIDs keep distinct pseudonyms)."""
    if isinstance(value, (list, tuple)):
        return [_pseudonymize_uid_value(item, research_project) for item in value]
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return value
    return pseudonymize_uid(text, research_project)

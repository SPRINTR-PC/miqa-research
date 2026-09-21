"""Discovery/parse stage: identify and parse a single DICOM instance from raw bytes.

Detection per the #98 spec: a metadata-only parse first, then a full-parse
fallback (``force=True``) for files missing the standard 128-byte preamble;
anything that still cannot be identified as DICOM is treated as non-DICOM.
"""
import io

import pydicom
from pydicom.dataset import Dataset


class NotADicomError(Exception):
    """The bytes are not a recognizable DICOM instance."""


def parse_dicom(raw_bytes: bytes) -> Dataset:
    """Parse `raw_bytes` into a pydicom Dataset (without pixel data).

    Raises NotADicomError when the content is not DICOM at all.
    """
    dataset = None
    for force in (False, True):
        try:
            dataset = pydicom.dcmread(io.BytesIO(raw_bytes), force=force, stop_before_pixels=True)
            break
        except pydicom.errors.InvalidDicomError:
            if force:
                raise NotADicomError("file does not look like DICOM") from None
    if not _looks_like_dicom(dataset):
        raise NotADicomError("file has no DICOM identity tags (SOP Instance UID missing)")
    return dataset


def _looks_like_dicom(dataset: Dataset | None) -> bool:
    """Cheap sanity check: a recognizable DICOM instance identifies its SOP instance."""
    if not isinstance(dataset, Dataset):
        return False
    sop_instance_uid = dataset.get("SOPInstanceUID") or getattr(
        dataset.file_meta, "MediaStorageSOPInstanceUID", ""
    )
    return bool(str(sop_instance_uid).strip())

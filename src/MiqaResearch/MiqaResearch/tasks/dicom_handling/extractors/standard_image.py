"""Standard radiology image extractor: image-plane geometry columns (#110).

Dispatched for the well-known standard image SOP Classes (CT, MR, X-ray, CR,
US, NM, PET, secondary capture); everything else falls through to the generic
extractor. Geometry is populated only from the standard image-plane tags —
a standard image missing them simply leaves the columns null.
"""
from pydicom.dataset import Dataset

from helpers.dicom_uid import pseudonymize_uid

from .generic import extract as generic_extract

STANDARD_IMAGE_SOP_CLASSES: frozenset[str] = frozenset({
    "1.2.840.10008.5.1.4.1.1.1.1",   # Digital X-Ray Image (For Presentation)
    "1.2.840.10008.5.1.4.1.1.1.1.1",  # Digital X-Ray Image (For Processing)
    "1.2.840.10008.5.1.4.1.1.2",      # CT Image
    "1.2.840.10008.5.1.4.1.1.2.1",    # Enhanced CT Image
    "1.2.840.10008.5.1.4.1.1.2.2",    # Legacy Converted Enhanced CT Image
    "1.2.840.10008.5.1.4.1.1.4",      # MR Image
    "1.2.840.10008.5.1.4.1.1.4.1",    # Enhanced MR Image
    "1.2.840.10008.5.1.4.1.1.4.4",    # Legacy Converted Enhanced MR Image
    "1.2.840.10008.5.1.4.1.1.6.1",    # Ultrasound Image
    "1.2.840.10008.5.1.4.1.1.7",      # Secondary Capture Image
    "1.2.840.10008.5.1.4.1.1.7.1",    # Multi-frame Single-bit Secondary Capture
    "1.2.840.10008.5.1.4.1.1.7.2",    # Multi-frame Grayscale Byte Secondary Capture
    "1.2.840.10008.5.1.4.1.1.7.3",    # Multi-frame Grayscale Word Secondary Capture
    "1.2.840.10008.5.1.4.1.1.7.4",    # Multi-frame True-color Secondary Capture
    "1.2.840.10008.5.1.4.1.1.9",      # Computed Radiography Image
    "1.2.840.10008.5.1.4.1.1.12.1",   # X-Ray Angiographic Image
    "1.2.840.10008.5.1.4.1.1.12.2",   # X-Ray Radiofluoroscopic Image
    "1.2.840.10008.5.1.4.1.1.20",     # Nuclear Medicine Image
    "1.2.840.10008.5.1.4.1.1.128",    # PET Image
})


def extract(ds: Dataset, research_project) -> dict:
    result = generic_extract(ds, research_project)
    # ImageOrientationPatient is a 3-valued DS (row direction cosines), PS3.3 C.7.5.1.1
    result["image_orientation_patient"] = _decimal_list(ds.get("ImageOrientationPatient"), 3)
    result["image_position_patient"] = _decimal_list(ds.get("ImagePositionPatient"), 3)
    result["pixel_spacing"] = _decimal_list(ds.get("PixelSpacing"), 2)
    for_uid = str(ds.get("FrameOfReferenceUID") or "").strip()
    result["frame_of_reference_uid"] = pseudonymize_uid(for_uid, research_project) if for_uid else None
    return result


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

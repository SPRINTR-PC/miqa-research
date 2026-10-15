"""Standard radiology image extractor: image-plane geometry columns (#110).

Dispatched for the well-known standard image SOP Classes (CT, MR, X-ray, CR,
US, NM, PET, secondary capture); everything else falls through to the generic
extractor. Geometry is populated only from the standard image-plane tags —
a standard image missing them simply leaves the columns null.
"""
from pydicom.dataset import Dataset

from .common import image_geometry
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


def extract(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    result.update(image_geometry(ds, research_project))
    return result

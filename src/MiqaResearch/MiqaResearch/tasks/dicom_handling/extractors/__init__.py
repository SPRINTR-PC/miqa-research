"""Extraction registry: dispatch by SOP Class UID with generic fall-through (#110).

A file is never rejected for lacking a bespoke handler: any SOP Class without
a registered handler falls through to the generic extractor. Modality-specific
handlers (RDSR, radiotherapy, pathology) join the registry in later tickets
(#121/#124) without changing this dispatch.
"""
from collections.abc import Callable

from pydicom.dataset import Dataset

from . import generic, standard_image

# SOP Class UID -> handler. Standard radiology image classes share one handler.
EXTRACTOR_REGISTRY: dict[str, Callable] = {
    sop_class_uid: standard_image.extract for sop_class_uid in standard_image.STANDARD_IMAGE_SOP_CLASSES
}

DEFAULT_EXTRACTOR = generic.extract


def extract(ds: Dataset, research_project) -> dict:
    """Extract file-level data for one parsed instance.

    Returns a dict with the common keys from common.common_extraction
    (study_datetime, study_description, series_description, modality,
    contains_burned_in_annotations, metadata) plus, for standard image SOP
    classes, the image-geometry keys (image_orientation_patient,
    image_position_patient, pixel_spacing, frame_of_reference_uid).
    """
    sop_class_uid = str(ds.get("SOPClassUID") or "").strip()
    handler = EXTRACTOR_REGISTRY.get(sop_class_uid, DEFAULT_EXTRACTOR)
    return handler(ds, research_project)

"""Pathology WSI extractor (#124): pyramid/tiling metadata + functional-group geometry.

VL Whole Slide Microscopy Image Storage carries no ImageOrientationPatient/
ImagePositionPatient — those are patient-coordinate tags that don't apply to a
slide's coordinate system — so both stay null via common.image_geometry's own
top-level tag check. PixelSpacing instead lives inside the multi-frame
functional-groups macro (PS3.3 C.7.6.16.2.3): Shared when uniform across a
pyramid level's tiles, Per-Frame when it varies frame-to-frame — this handler
checks Shared first, then falls back to the first Per-Frame group.
FrameOfReferenceUID is still a top-level tag, shared across a slide's pyramid
levels, and populates the same way the generic handler's geometry helper
already does.
"""
from pydicom.dataset import Dataset

from .common import decimal_list, image_geometry
from .generic import extract as generic_extract


def extract(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    result.update(image_geometry(ds, research_project))
    result["pixel_spacing"] = _functional_group_pixel_spacing(ds)
    result["metadata"]["pathology_summary"] = _pyramid_summary(ds)
    return result


def _functional_group_pixel_spacing(ds: Dataset) -> list[float] | None:
    """PixelSpacing from the Shared, else the first Per-Frame, Pixel Measures macro."""
    for sequence_keyword in ("SharedFunctionalGroupsSequence", "PerFrameFunctionalGroupsSequence"):
        groups = ds.get(sequence_keyword) or []
        if not groups:
            continue
        measures_sequence = groups[0].get("PixelMeasuresSequence") or []
        if not measures_sequence:
            continue
        spacing = decimal_list(measures_sequence[0].get("PixelSpacing"), 2)
        if spacing is not None:
            return spacing
    return None


def _pyramid_summary(ds: Dataset) -> dict:
    image_type = list(ds.get("ImageType") or [])
    optical_paths = ds.get("OpticalPathSequence") or []
    return {
        "frame_count": _int(ds.get("NumberOfFrames")),
        "tile_rows": _int(ds.get("Rows")),
        "tile_columns": _int(ds.get("Columns")),
        "total_pixel_matrix_rows": _int(ds.get("TotalPixelMatrixRows")),
        "total_pixel_matrix_columns": _int(ds.get("TotalPixelMatrixColumns")),
        # Third ImageType value per PS3.3 C.8.12.4: VOLUME/LABEL/OVERVIEW/THUMBNAIL.
        "image_type": image_type[2] if len(image_type) > 2 else None,
        "optical_path_count": len(optical_paths),
        "objective_lens_power": _float(optical_paths[0].get("ObjectiveLensPower")) if optical_paths else None,
    }


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

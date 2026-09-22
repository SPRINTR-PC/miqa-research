"""Declared-pixel-dimension plausibility guard (#114, #127).

A file's *declared* Rows/Columns/pixel-matrix dimensions or NumberOfFrames
are rejected here, before any pixel data is decoded -- defense against a
small compressed payload declaring an enormous decoded size (a
decompression-bomb shape, especially relevant to pathology J2K frames).
`dicom_parsing.parse_dicom` never reads PixelData at all
(`stop_before_pixels=True`), so this check is purely a header-tag read.
"""
from pydicom.dataset import Dataset


class ImplausiblePixelDimensionsError(Exception):
    """A file's declared pixel dimensions or frame count exceed the
    configured plausibility bounds."""


# Header tags carrying a *declared* pixel-grid dimension.
_DIMENSION_KEYWORDS = ("Rows", "Columns", "TotalPixelMatrixRows", "TotalPixelMatrixColumns")


def assert_plausible_pixel_dimensions(dataset: Dataset, max_pixel_dimension: int, max_frame_count: int) -> None:
    """Raise ImplausiblePixelDimensionsError when any declared dimension or
    the declared frame count exceeds the configured bounds."""
    for keyword in _DIMENSION_KEYWORDS:
        value = _as_int(dataset.get(keyword))
        if value is not None and value > max_pixel_dimension:
            raise ImplausiblePixelDimensionsError(
                f"declared {keyword}={value} exceeds the configured maximum of {max_pixel_dimension} pixels"
            )
    frame_count = _as_int(dataset.get("NumberOfFrames"))
    if frame_count is not None and frame_count > max_frame_count:
        raise ImplausiblePixelDimensionsError(
            f"declared NumberOfFrames={frame_count} exceeds the configured maximum of {max_frame_count} frames"
        )


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

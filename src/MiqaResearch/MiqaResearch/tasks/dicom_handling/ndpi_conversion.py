"""Standalone *.ndpi -> DICOM converter (#125).

Independently invocable: converts a Hamamatsu *.ndpi whole-slide image into a
VL Whole Slide Microscopy Image IOD DICOM file set on disk. Nothing in
`pipeline.run_ingestion` calls this -- an *.ndpi source is just an
unparseable file to the ingestion pipeline, like any other non-DICOM
content, so ingestion runs never trigger a conversion.

Wraps `wsidicomizer.WsiDicomizer.convert` (selected per #107's tooling
research) for its explicit lossless Hamamatsu NDPI support (via `opentile`)
and its purpose-built targeting of the VL WSI IOD / SOP Class UID
1.2.840.10008.5.1.4.1.1.77.1.6 that this repo's WADO-RS path already expects.
"""
from pathlib import Path

from wsidicomizer import WsiDicomizer


class NdpiConversionError(Exception):
    """The *.ndpi file could not be converted to a DICOM file set."""


class NdpiSourceNotFoundError(NdpiConversionError):
    """The ndpi source path does not exist."""


class NdpiUnsupportedSourceError(NdpiConversionError):
    """The source path is not a .ndpi file."""


def convert_ndpi_to_dicom(ndpi_path: Path, output_dir: Path) -> list[Path]:
    """Convert `ndpi_path` into a DICOM file set written under `output_dir`.

    Returns the paths of the produced DICOM files. `output_dir` is created if
    missing. Raises NdpiSourceNotFoundError / NdpiUnsupportedSourceError for a
    bad source, or NdpiConversionError wrapping any failure raised by the
    underlying conversion library.
    """
    ndpi_path = Path(ndpi_path)
    output_dir = Path(output_dir)
    if not ndpi_path.is_file():
        raise NdpiSourceNotFoundError(f"ndpi source not found: {ndpi_path}")
    if ndpi_path.suffix.lower() != ".ndpi":
        raise NdpiUnsupportedSourceError(f"source is not a .ndpi file: {ndpi_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        produced = WsiDicomizer.convert(ndpi_path, output_path=output_dir)
    except Exception as exc:
        raise NdpiConversionError(f"failed to convert {ndpi_path}: {exc}") from exc
    return [Path(path) for path in produced]

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
from contextlib import contextmanager
from pathlib import Path

import pydicom.config as _pydicom_config

# Importing wsidicomizer sets pydicom's *global*, process-wide validation config to
# strict (wsidicomizer.dicomizer_source runs `config.enforce_valid_values = True` and
# `config.future_behavior()` at module scope, unscoped, with nothing to undo it) --
# left as-is, this would stricten every other DICOM read/write sharing the process for
# good, including the ingestion pipeline's tolerant handling of real-world
# non-conformant tag values. Snapshot before the import and restore right after, so
# merely importing this module has no lasting effect on the rest of the process.
_reading_mode_before_import = _pydicom_config.settings.reading_validation_mode
_writing_mode_before_import = _pydicom_config.settings.writing_validation_mode
_enforce_valid_values_before_import = _pydicom_config.enforce_valid_values
_use_future_before_import = _pydicom_config._use_future

from wsidicomizer import WsiDicomizer  # noqa: E402

_pydicom_config.settings.reading_validation_mode = _reading_mode_before_import
_pydicom_config.settings.writing_validation_mode = _writing_mode_before_import
_pydicom_config.enforce_valid_values = _enforce_valid_values_before_import
_pydicom_config.future_behavior(_use_future_before_import)


class NdpiConversionError(Exception):
    """The *.ndpi file could not be converted to a DICOM file set."""


class NdpiSourceNotFoundError(NdpiConversionError):
    """The ndpi source path does not exist."""


class NdpiUnsupportedSourceError(NdpiConversionError):
    """The source path is not a .ndpi file."""


@contextmanager
def _wsidicomizer_strict_validation():
    """Re-apply the strict pydicom validation wsidicomizer expects (see the module
    docstring above) for the duration of one conversion call only, then restore
    whatever this process had before -- so a conversion never leaves the rest of the
    process stricter than it found it.
    """
    reading_mode = _pydicom_config.settings.reading_validation_mode
    writing_mode = _pydicom_config.settings.writing_validation_mode
    enforce_valid_values = _pydicom_config.enforce_valid_values
    use_future = _pydicom_config._use_future
    _pydicom_config.enforce_valid_values = True
    _pydicom_config.future_behavior()
    try:
        yield
    finally:
        _pydicom_config.settings.reading_validation_mode = reading_mode
        _pydicom_config.settings.writing_validation_mode = writing_mode
        _pydicom_config.enforce_valid_values = enforce_valid_values
        _pydicom_config.future_behavior(use_future)


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
        with _wsidicomizer_strict_validation():
            produced = WsiDicomizer.convert(ndpi_path, output_path=output_dir)
    except Exception as exc:
        raise NdpiConversionError(f"failed to convert {ndpi_path}: {exc}") from exc
    return [Path(path) for path in produced]

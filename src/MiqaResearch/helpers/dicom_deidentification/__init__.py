"""The De-identification Profile sanitizer (ADR 0028, #273).

One sanitizer for every place the platform exposes DICOM headers: the
ingestion metadata dump, WADO-RS `/metadata` and viewer-built SR/SEG
re-ingest. Callers parse a header, call `deidentify`, then serialize the
result (`to_json_dict()` for WADO, `build_metadata_dump` for the dump).
"""
from .sanitizer import deidentify

__all__ = ["deidentify"]

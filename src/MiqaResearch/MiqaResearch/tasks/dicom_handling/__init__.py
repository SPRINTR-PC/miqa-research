"""DICOM ingestion pipeline stages (#98 spec).

`pipeline.run_ingestion` is the top-level, directly-callable seam; the stage
modules alongside it (parsing, participant matching, extraction, records,
storage) are its internals.
"""

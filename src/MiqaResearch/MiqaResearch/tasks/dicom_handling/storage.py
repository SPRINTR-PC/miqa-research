"""Storage stage: write the ingested file's bytes to the DicomFile's file field.

Local deployment storage by default (#119); the S3-compatible object storage
option (#122) slots in here via a dedicated named storage for imaging files.
"""
from django.core.files.base import ContentFile

from MiqaResearch.data.models import DicomFile


def store_file_bytes(dcm_file: DicomFile, raw_bytes: bytes) -> None:
    """Store the original file bytes on the record (without saving the row yet).

    The model's upload_to places it under DICOM/{year}/{month}/{series id}/;
    the caller saves the row afterward.
    """
    dcm_file.file.save(f"{dcm_file.id}.dcm", ContentFile(raw_bytes), save=False)


def replace_file_bytes(dcm_file: DicomFile, raw_bytes: bytes) -> str:
    """Store new bytes on the record (without saving the row); return the superseded file name.

    The caller deletes the superseded file (`discard_file`) only after the row
    is saved, so a rolled-back update never loses the stored original.
    """
    old_name = dcm_file.file.name
    store_file_bytes(dcm_file, raw_bytes)
    return old_name


def discard_file(dcm_file: DicomFile, name: str) -> None:
    """Delete a superseded stored file."""
    if name and name != dcm_file.file.name:
        dcm_file.file.storage.delete(name)

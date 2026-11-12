"""The stored original DICOM files behind a Participant Key (#421).

Narrow seam for `fill_demographics`: it needs the un-deidentified headers, which live only in the stored
originals (`DicomFile.file`, written to DicomStorage by the dicom_instance loader, #418). If #418 adds a
generic originals reader, point `open_original_dicom_files` at it and keep this signature.
"""
from collections.abc import Iterator
from typing import BinaryIO

from MiqaResearch.data.models import DicomFile, ParticipantKey


def open_original_dicom_files(key: ParticipantKey) -> Iterator[BinaryIO]:
    """Each stored original of the key's Studies as an open binary file, one at a time (lazily, so a
    caller that found what it needed can stop; the file closes when the next one is requested).
    A file that cannot be opened is skipped."""
    for dicom_file in DicomFile.objects.filter(series__study__participant_key=key).order_by("id").iterator():
        try:
            handle = dicom_file.file.open("rb")
        except OSError:
            continue
        with handle:
            yield handle

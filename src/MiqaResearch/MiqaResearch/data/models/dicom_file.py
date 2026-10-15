from datetime import datetime
from uuid import uuid7

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .dicom_series import DicomSeries
from .dicom_storage import DicomStorage
from .research_project import ResearchProject


def upload_to(instance, filename):
    now = datetime.now()
    return f"DICOM/{now.year}/{now.month:02}/{instance.series.id}/{instance.id}.dcm"


class DicomFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    series = models.ForeignKey(DicomSeries, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    sop_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    research_project = models.ForeignKey(ResearchProject, on_delete=models.PROTECT, blank=True, null=True, db_index=True)
    file = models.FileField(upload_to=upload_to, storage=DicomStorage(), blank=False, null=False)
    # 3-valued per PS3.3 C.7.5.1.1 (row direction cosines), not 6
    image_orientation_patient = ArrayField(models.FloatField(), size=3, blank=True, null=True)
    image_position_patient = ArrayField(models.FloatField(), size=3, blank=True, null=True)
    frame_of_reference_uid = models.CharField(max_length=128, blank=True, null=True)
    pixel_spacing = ArrayField(models.FloatField(), size=2, blank=True, null=True)
    contains_burned_in_annotations = models.BooleanField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    file_size_in_mb = models.FloatField(blank=False, null=False, help_text="The size of this file in MB")
    content_sha256 = models.CharField(
        max_length=64, blank=True, null=False, default="",
        help_text="SHA-256 hex of the stored original file bytes; detects duplicate files whose content differs from what's stored")
    transfer_syntax_uid = models.CharField(
        max_length=64, blank=True, null=True,
        help_text="Transfer Syntax UID of the stored file; WADO-RS /frames serves frames in this syntax, never transcoded")
    frame_index = models.JSONField(
        blank=True, null=True,
        help_text="Frame offset index: [offset, length] per frame in the stored file (tasks/dicom_handling/frame_index.py); "
                  "null = not built yet, [] = no servable frames")
    uids_pseudonymized = models.BooleanField(
        default=False,
        help_text="The stored bytes already carry pseudonymized UIDs (viewer-saved Annotations/Segmentations, #287); "
                  "serve-time de-identification must not hash them again (uids_already_pseudonymized=True)")

    class Meta:
        db_table = "mires_dicom_file"
        ordering = ["series", "-id"]
        indexes = [
            GinIndex(
                fields=['metadata'],
                name='metadata_gin_idx',
                opclasses=['jsonb_path_ops'],
            )
        ]

    def __str__(self):
        return self.sop_instance_uid

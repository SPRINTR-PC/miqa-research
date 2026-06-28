from datetime import datetime
from uuid import uuid7

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .research_project import ResearchProject
from .dicom_series import DicomSeries


def upload_to(instance, filename):
    now = datetime.now()
    return f"DICOM/{now.year}/{now.month:02}/{instance.series.id}/{instance.id}.dcm"


class DicomFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    series = models.ForeignKey(DicomSeries, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    sop_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    research_project = models.ForeignKey(ResearchProject, on_delete=models.PROTECT, blank=True, null=True, db_index=True)
    file = models.FileField(upload_to=upload_to, blank=False, null=False)
    image_orientation_patient = ArrayField(models.FloatField(), size=6, blank=True, null=True)
    frame_of_reference_uid = models.CharField(max_length=128, blank=True, null=True)
    pixel_spacing = ArrayField(models.FloatField(), size=2, blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)

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

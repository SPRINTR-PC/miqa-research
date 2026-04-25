from uuid import uuid7

from django.db import models

from .dicom_study import DicomStudy


class DicomSeries(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    study = models.ForeignKey(DicomStudy, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    series_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    series_description = models.CharField(max_length=128, blank=True, null=True)
    modality = models.CharField(max_length=12, blank=True, null=True)

    class Meta:
        db_table = "mires_dicom_series"
        ordering = ['-id']
        unique_together = [("study", "series_instance_uid", "modality")]
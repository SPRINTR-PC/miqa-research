from uuid import uuid7

from django.db import models

from .patient import Patient


class DicomStudy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    study_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    study_description = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = "mires_dicom_study"
        ordering = ['-id']
from uuid import uuid7

from django.db import models

from .concept import Concept
from .dicom_study import DicomStudy


class DicomSeries(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    study = models.ForeignKey(DicomStudy, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    series_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    series_description = models.CharField(max_length=128, blank=True, null=True)
    modality = models.CharField(max_length=12, blank=True, null=True)
    anatomic_site_concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, blank=True, null=True)
    wadors_uri = models.URLField(max_length=512, blank=True, null=True,
                                 help_text="The WADO-RS URI for retrieving the imaging series")


    class Meta:
        db_table = "mires_dicom_series"
        ordering = ['-id']
        unique_together = [("study", "series_instance_uid", "modality")]
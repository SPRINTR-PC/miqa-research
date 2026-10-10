from uuid import uuid7

from django.db import models

from .concept import Concept
from .dicom_study import DicomStudy


class DicomSeries(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    study = models.ForeignKey(DicomStudy, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    series_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    series_description = models.CharField(max_length=128, blank=True, null=True)  # noqa: DJ001
    modality = models.CharField(max_length=12, blank=True, null=True)  # noqa: DJ001
    anatomic_site_concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, blank=True, null=True)
    file_size_in_mb = models.FloatField(blank=True, null=True, help_text="Sum of file_size_in_mb across this series' DicomFile rows")
    frame_of_reference_uid = models.CharField(  # noqa: DJ001
        max_length=128, blank=True, null=True, db_index=True,
        help_text="Pseudonymized Frame of Reference UID shared by every file of the series; null if absent or mixed",
    )


    class Meta:
        db_table = "mires_dicom_series"
        ordering = ['-id']
        unique_together = [("study", "series_instance_uid", "modality")]

    def __str__(self) -> str:
        return f"{self.series_instance_uid} - {self.series_description}"

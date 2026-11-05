from uuid import uuid7

from django.db import models

from .concept import Concept
from .study_participant import StudyParticipant
from .visit_occurrence import VisitOccurrence


class DicomStudy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    study_participant = models.ForeignKey(StudyParticipant, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    visit_occurrence = models.ForeignKey(
        VisitOccurrence,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="dicom_studies",
        help_text="The visit during which this study was performed."
    )
    study_datetime = models.DateTimeField(blank=False, null=False)
    study_instance_uid = models.CharField(max_length=128, blank=False, null=False, unique=True)
    study_description = models.CharField(max_length=200, blank=True, null=True)
    procedure_concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        db_table = "mires_dicom_study"
        ordering = ['-id']

    def __str__(self):
        return f"{self.study_instance_uid} ({self.study_description}, {self.study_datetime:%Y-%m-%d %H:%M:%S})"

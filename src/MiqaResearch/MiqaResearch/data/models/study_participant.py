from uuid import uuid7

from django.db import models

from helpers.db_fields import SearchableEncryptedCharField
from .research_project import ResearchProject
from ..managers.study_participant_manager import StudyParticipantManager

class StudyParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    person_source_value = SearchableEncryptedCharField(
        blank=True, null=True, help_text="The original primary identifier of study participant")
    name = SearchableEncryptedCharField(blank=True, null=True, help_text="The full name of the participant")
    study_id = models.CharField(max_length=100, blank=False, null=False)
    year_of_birth = models.IntegerField(blank=True, null=True)
    month_of_birth = models.IntegerField(blank=True, null=True)
    day_of_birth = models.IntegerField(blank=True, null=True)
    gender = models.CharField(
        max_length=10, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other'), ('U', 'Unknown')],
        blank=False, null=False, default='U')
    research_project = models.ForeignKey(ResearchProject, on_delete=models.PROTECT, blank=True, null=True, db_index=True)

    objects = StudyParticipantManager()

    class Meta:
        db_table = "mires_study_participant"
        ordering = ["study_id"]
        unique_together = [("study_id", "research_project")]

    def __str__(self):
        return f"{self.study_id} ({self.gender})"
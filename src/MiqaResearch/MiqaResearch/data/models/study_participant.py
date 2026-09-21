from uuid import uuid7

from django.db import models

from helpers.db_fields import SearchableEncryptedCharField

from ..managers.study_participant_manager import StudyParticipantManager
from .research_project import ResearchProject


class StudyParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    person_source_value = SearchableEncryptedCharField(
        blank=True, null=True, help_text="The original primary identifier of study participant")
    name = SearchableEncryptedCharField(blank=True, null=True, help_text="The full name of the participant")
    alias1 = models.CharField(max_length=100, blank=False, null=False, unique=True)
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
        ordering = ["alias1"]
        unique_together = [("alias1", "research_project")]

    def __str__(self):
        return f"{self.alias1} ({self.gender})"
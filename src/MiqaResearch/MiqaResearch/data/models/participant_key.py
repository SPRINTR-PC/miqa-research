from uuid import uuid7

from django.db import models

from contract.constants.participant_key import LINK_VIA_CHOICES
from helpers.db_fields import SearchableEncryptedCharField

from .etl_job import EtlJob
from .research_project import ResearchProject
from .study_participant import StudyParticipant


class ParticipantKey(models.Model):
    """One identifier value of one kind within a Research Project, maybe not yet linked (ADR 0035)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(ResearchProject, on_delete=models.PROTECT, related_name="participant_keys")
    key_type = models.CharField(max_length=100, help_text="`<source>:<attribute>`, e.g. dicom:PatientID")
    value = SearchableEncryptedCharField(help_text="Trimmed, case preserved", hash_field_name="value_hash")
    study_participant = models.ForeignKey(
        StudyParticipant, on_delete=models.CASCADE, null=True, blank=True, related_name="participant_keys"
    )
    first_seen_job = models.ForeignKey(
        EtlJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    linked_via = models.CharField(max_length=10, choices=LINK_VIA_CHOICES, blank=True, default="")
    linked_job = models.ForeignKey(EtlJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    linked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_participant_key"
        constraints = [
            models.UniqueConstraint(fields=["project", "key_type", "value_hash"], name="mires_participant_key_unique"),
        ]

    def __str__(self):
        return f"{self.key_type} key {self.pk}"

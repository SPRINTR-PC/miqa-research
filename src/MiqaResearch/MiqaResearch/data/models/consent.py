from uuid import uuid7

from django.db import models

from .clinic import Clinic


class ParticipantConsentType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    label = models.CharField(
        max_length=255, unique=True, help_text="Short label for the consent type to display in the UI")
    short_label = models.CharField(  # noqa: DJ001
        max_length=40, blank=True, null=True, help_text="Short label for the consent type to display in the UI")
    description = models.TextField(blank=True, null=False, default="", help_text="Description of the consent type")
    research_project = models.ForeignKey(
        "ResearchProject", on_delete=models.CASCADE, blank=False, null=False, db_index=True)

    class Meta:
        db_table = "mires_participant_consent_type"
        verbose_name = "Participant Consent Type"
        verbose_name_plural = "Participant Consent Types"
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.research_project})"


class ParticipantConsent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    study_participant = models.ForeignKey("StudyParticipant", on_delete=models.CASCADE, blank=False, null=False,
                                          db_index=True)
    status = models.CharField(max_length=200, blank=True, null=True)  # noqa: DJ001
    consent_signed_date = models.DateTimeField(null=False, blank=False, help_text="Date and time when the consent was granted")
    last_updated = models.DateTimeField(auto_now=True, help_text="Date and time when the consent was last updated")
    consent_revoked_date = models.DateTimeField(null=True, blank=True, help_text="Date and time when the consent was revoked")
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, blank=False, null=False,)
    consent_type = models.ForeignKey(ParticipantConsentType, on_delete=models.CASCADE, blank=False, null=False,
                                     related_name="consents", related_query_name="consent",
                                     db_index=True)
    participant_information_version = models.CharField(max_length=100, blank=True, null=True)  # noqa: DJ001
    source = models.CharField(max_length=200, blank=True, null=True, help_text="Source of the consent")  # noqa: DJ001
    extra_info = models.JSONField(blank=True, null=True, help_text="Extra information about the consent")

    class Meta:
        db_table = "mires_participant_consent"
        verbose_name = "Participant Consent"
        verbose_name_plural = "Participant Consents"
        ordering = ["-consent_signed_date"]
        unique_together = [("study_participant", "consent_signed_date", "consent_type")]

    def __str__(self) -> str:
        return  f"{self.study_participant} - {self.consent_type} ({self.status})"


class ConsentDailyActiveSummary(models.Model):
    research_project = models.ForeignKey(
        "ResearchProject",
        on_delete=models.CASCADE,
        related_name="consent_daily_active_summaries",
    )
    clinic = models.ForeignKey(
        "Clinic",
        on_delete=models.CASCADE,
        related_name="consent_daily_active_summaries",
    )
    day = models.DateField()
    active_participant_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mires_consent_daily_active_summary"
        verbose_name = "Consent Daily Active Summary"
        verbose_name_plural = "Consent Daily Active Summaries"
        constraints = [
            models.UniqueConstraint(
                fields=["research_project", "clinic", "day"],
                name="unique_consent_daily_active_summary",
            ),
        ]
        indexes = [
            models.Index(fields=["research_project", "clinic", "day"]),
            models.Index(fields=["research_project", "day"]),
        ]
        ordering = ["research_project", "clinic", "day"]

    def __str__(self) -> str:
        return f"ConsentDailyActiveSummary(project={self.research_project}, clinic={self.clinic}, day={self.day}, active_participant_count={self.active_participant_count})"

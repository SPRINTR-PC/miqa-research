from uuid import uuid7

from django.db import models

from .research_project import ResearchProject


class EtlProjectSettings(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.OneToOneField(
        ResearchProject, on_delete=models.CASCADE, related_name="etl_settings", blank=False, null=False)
    log_retention_days = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Overrides MIRES_ETL_LOG_RETENTION_DAYS for this project; null defers to the global setting.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mires_etl_project_settings"
        ordering = ["project"]

    def __str__(self):
        return f"ETL settings for {self.project}"

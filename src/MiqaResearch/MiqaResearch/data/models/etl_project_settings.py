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
    max_script_source_bytes = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Overrides MIRES_ETL_SCRIPT_MAX_SOURCE_BYTES for this project's EtlScriptVersions; "
                   "null defers to the global default.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mires_etl_project_settings"
        ordering = ["project"]

    def __str__(self):
        return f"ETL settings for {self.project}"


def get_max_script_source_bytes(project):
    """The max size, in bytes, an EtlScriptVersion.source may be for `project`:
    that project's EtlProjectSettings.max_script_source_bytes if set, else the
    global MIRES_ETL_SCRIPT_MAX_SOURCE_BYTES default. A native script has no
    project, and so always uses the global default."""
    from django.conf import settings as django_settings

    if project is not None:
        override = (
            EtlProjectSettings.objects
            .filter(project=project)
            .values_list("max_script_source_bytes", flat=True)
            .first()
        )
        if override is not None:
            return override

    return django_settings.ETL_SCRIPT_MAX_SOURCE_BYTES

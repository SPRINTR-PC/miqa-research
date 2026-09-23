from uuid import uuid7

from django.db import models

from .etl_script import EtlScriptVersion
from .research_project import ResearchProject


class PipelineBinding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name="etl_pipeline_bindings",
        blank=False, null=False, db_index=True)
    source_bucket = models.CharField(max_length=200, blank=False, null=False)
    source_prefix = models.CharField(max_length=500, blank=True, default="")
    script_version = models.ForeignKey(
        EtlScriptVersion, on_delete=models.PROTECT, related_name="pipeline_bindings", blank=False, null=False,
        help_text="The pinned Script Version this Binding runs; a script edit elsewhere never changes it.")
    raw_bucket = models.CharField(max_length=200, blank=False, null=False)
    raw_prefix = models.CharField(max_length=500, blank=True, default="")
    timeout_seconds_override = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Overrides the platform default sandbox timeout for this Binding; may only lower it, never raise it.")
    memory_mb_override = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Overrides the platform default sandbox memory limit for this Binding; "
                   "may only lower it, never raise it.")
    cpu_millicores_override = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Overrides the platform default sandbox CPU limit for this Binding; "
                   "may only lower it, never raise it.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mires_etl_pipeline_binding"
        ordering = ["project", "source_bucket", "source_prefix"]
        unique_together = [("source_bucket", "source_prefix")]

    def __str__(self):
        return f"{self.source_bucket}/{self.source_prefix}"

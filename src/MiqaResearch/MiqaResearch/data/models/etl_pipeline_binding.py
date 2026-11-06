from uuid import uuid7

from django.db import models
from django.db.models import Q

from contract.constants.etl import (
    PIPELINE_BINDING_GROUPING_CHOICES,
    PIPELINE_BINDING_GROUPING_FILE,
    PIPELINE_BINDING_RAW_RETENTION_CHOICES,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
)

from .etl_script import EtlScriptVersion
from .etl_source_location import EtlSourceLocation
from .etl_storage import EtlStorage, default_storage_id
from .research_project import ResearchProject


class PipelineBinding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name="etl_pipeline_bindings",
        blank=False, null=False, db_index=True)
    storage = models.ForeignKey(
        EtlStorage, on_delete=models.PROTECT, related_name="pipeline_bindings", blank=False, null=False,
        default=default_storage_id)
    source_bucket = models.CharField(max_length=200, blank=False, null=False)
    source_prefix = models.CharField(max_length=500, blank=True, default="")
    source_location = models.ForeignKey(
        EtlSourceLocation, on_delete=models.PROTECT, related_name="bindings", blank=True, null=True,
        help_text="The Source Location the source bucket/prefix was copied from (#268); null for older Bindings.")
    grouping_mode = models.CharField(
        max_length=10, choices=PIPELINE_BINDING_GROUPING_CHOICES, default=PIPELINE_BINDING_GROUPING_FILE,
        blank=False, null=False,
        help_text="\"file\": each new source file queues its own Job immediately. \"folder\": each "
                   "immediate child directory under source_prefix is tracked to quiescence before "
                   "queueing one Job for the whole directory.")
    quiescence_seconds = models.PositiveIntegerField(
        default=300,
        help_text="Folder-grouped bindings only: how long a directory must see no new files before "
                   "its Job is queued.")
    config = models.JSONField(
        default=dict, blank=True,
        help_text="Config values passed to the Script's manifest.json and snapshotted onto every EtlJob "
                   "queued from this Binding.")
    script_version = models.ForeignKey(
        EtlScriptVersion, on_delete=models.PROTECT, related_name="pipeline_bindings", blank=False, null=False,
        help_text="The pinned Script Version this Binding runs; a script edit elsewhere never changes it.")
    raw_retention = models.CharField(
        max_length=10, choices=PIPELINE_BINDING_RAW_RETENTION_CHOICES, default=PIPELINE_BINDING_RAW_RETENTION_MOVE,
        blank=False, null=False,
        help_text="\"move\": a successful Job's inputs are moved to raw_bucket. \"delete\": they are deleted "
                   "from the source after the load commits and never copied (ADR 0032). Snapshotted onto "
                   "every EtlJob queued from this Binding.")
    raw_bucket = models.CharField(
        max_length=200, blank=True, default="", help_text="Required for \"move\" Raw Retention; blank for \"delete\".")
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
        unique_together = [("storage", "source_bucket", "source_prefix")]
        constraints = [
            # "move" needs somewhere to move to; "delete" keeps no raw destination at all (#246).
            models.CheckConstraint(
                condition=(Q(raw_retention=PIPELINE_BINDING_RAW_RETENTION_MOVE) & ~Q(raw_bucket=""))
                | (Q(raw_retention=PIPELINE_BINDING_RAW_RETENTION_DELETE) & Q(raw_bucket="") & Q(raw_prefix="")),
                name="mires_etl_binding_raw_destination_matches_retention",
            ),
        ]

    def __str__(self):
        return f"{self.source_bucket}/{self.source_prefix}"

    def job_snapshot(self) -> dict:
        """The Binding settings every EtlJob queued from it freezes, so a later edit never
        changes a queued Job (#224, #246)."""
        return {"config_snapshot": self.config, "raw_retention": self.raw_retention}

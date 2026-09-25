from uuid import uuid7

from django.db import models

from .etl_pipeline_binding import PipelineBinding


class EtlPendingGroup(models.Model):
    """The orchestrator's (#162) own quiescence tracker for a folder-grouped `PipelineBinding`:
    one row per immediate child directory under the Binding's `source_prefix` that currently has
    unqueued files. `last_seen_at` is bumped to the poll time whenever that poll discovers a new
    file under the directory; once `last_seen_at` is at least `binding.quiescence_seconds` in the
    past, the directory is quiescent and its files are queued as one Job, after which this row is
    deleted -- a later drop into the same directory starts a fresh quiescence window.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    binding = models.ForeignKey(
        PipelineBinding, on_delete=models.CASCADE, related_name="pending_groups", blank=False, null=False,
        db_index=True)
    group_key = models.CharField(
        max_length=500, blank=True, default="",
        help_text="The immediate child directory name (relative to the Binding's source_prefix); "
                   "empty for files sitting directly under source_prefix with no subdirectory.")
    last_seen_at = models.DateTimeField(
        help_text="Poll time of the most recently discovered new file in this group.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_pending_group"
        ordering = ["binding", "group_key"]
        unique_together = [("binding", "group_key")]

    def __str__(self):
        return f"{self.binding} :: {self.group_key or '(root)'}"

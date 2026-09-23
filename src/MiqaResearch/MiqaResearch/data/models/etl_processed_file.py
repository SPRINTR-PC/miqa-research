from uuid import uuid7

from django.db import models

from .etl_pipeline_binding import PipelineBinding


class EtlProcessedFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    binding = models.ForeignKey(
        PipelineBinding, on_delete=models.CASCADE, related_name="processed_files",
        blank=False, null=False, db_index=True)
    bucket = models.CharField(max_length=200, blank=False, null=False)
    key = models.CharField(max_length=1000, blank=False, null=False)
    etag = models.CharField(max_length=100, blank=True, default="")
    last_modified = models.DateTimeField(blank=True, null=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_processed_file"
        ordering = ["binding", "bucket", "key"]
        unique_together = [("binding", "bucket", "key")]

    def __str__(self):
        return f"{self.bucket}/{self.key}"

from uuid import uuid7

from django.db import models

from contract.constants.etl import ETL_JOB_STATUS_CHOICES, ETL_JOB_STATUS_PENDING

from .etl_pipeline_binding import PipelineBinding
from .etl_script import EtlScriptVersion


class EtlJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    binding = models.ForeignKey(
        PipelineBinding, on_delete=models.PROTECT, related_name="jobs", blank=False, null=False, db_index=True)
    script_version = models.ForeignKey(
        EtlScriptVersion, on_delete=models.PROTECT, related_name="jobs", blank=False, null=False,
        help_text="The Script Version that actually ran for this attempt.")
    status = models.CharField(
        max_length=10, choices=ETL_JOB_STATUS_CHOICES, default=ETL_JOB_STATUS_PENDING,
        blank=False, null=False, db_index=True)
    config_snapshot = models.JSONField(
        default=dict, blank=True, help_text="Snapshot of the Binding's config at the time this Job was queued.")
    sandbox_image_digest = models.CharField(max_length=200, blank=True, default="")
    log = models.TextField(
        blank=True, default="", help_text="Sandbox execution log, capped at 64 KB by the orchestrator.")
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_job"
        ordering = ["-created_at"]

    def __str__(self):
        return f"EtlJob {self.id} ({self.status})"


class EtlJobInput(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    job = models.ForeignKey(
        EtlJob, on_delete=models.CASCADE, related_name="inputs", blank=False, null=False, db_index=True)
    bucket = models.CharField(max_length=200, blank=False, null=False)
    key = models.CharField(max_length=1000, blank=False, null=False)
    sha256 = models.CharField(max_length=64, blank=False, null=False)
    size_bytes = models.BigIntegerField(blank=False, null=False)
    raw_bucket_key = models.CharField(
        max_length=1000, blank=True, default="",
        help_text="Populated once this input has been moved to the raw bucket.")
    moved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "mires_etl_job_input"
        ordering = ["job", "bucket", "key"]

    def __str__(self):
        return f"{self.bucket}/{self.key}"

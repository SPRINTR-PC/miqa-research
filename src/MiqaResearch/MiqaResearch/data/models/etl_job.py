from uuid import uuid7

from django.db import models
from django.db.models import Q

from contract.constants.etl import (
    ETL_JOB_INPUT_SOURCE_STATUS_CHOICES,
    ETL_JOB_INPUT_SOURCE_STATUS_PENDING,
    ETL_JOB_STATUS_CHOICES,
    ETL_JOB_STATUS_PENDING,
    ETL_JOB_STATUS_RUNNING,
    PIPELINE_BINDING_RAW_RETENTION_CHOICES,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
)

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
    attempt = models.PositiveIntegerField(
        default=1, help_text="1 for the original run; incremented for each capped auto-retry.")
    retry_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, related_name="retries", blank=True, null=True,
        help_text="The EtlJob this one automatically retries, for an infra-class failure. Null for attempt 1 "
                   "or a manual retry.")
    config_snapshot = models.JSONField(
        default=dict, blank=True, help_text="Snapshot of the Binding's config at the time this Job was queued.")
    raw_retention = models.CharField(
        max_length=10, choices=PIPELINE_BINDING_RAW_RETENTION_CHOICES, default=PIPELINE_BINDING_RAW_RETENTION_MOVE,
        blank=False, null=False,
        help_text="Snapshot of the Binding's Raw Retention at the time this Job was queued; a later Binding "
                   "change never affects this Job's inputs.")
    sandbox_image_digest = models.CharField(max_length=200, blank=True, default="")
    log = models.TextField(
        blank=True, default="", help_text="Sandbox execution log, capped at 64 KB by the orchestrator.")
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_job"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["binding"],
                condition=Q(status__in=[ETL_JOB_STATUS_PENDING, ETL_JOB_STATUS_RUNNING]),
                name="mires_etl_job_one_active_per_binding",
            ),
        ]

    def __str__(self):
        return f"EtlJob {self.id} ({self.status})"

    def snapshot(self) -> dict:
        """This Job's frozen Binding settings (see `PipelineBinding.job_snapshot`), carried
        unchanged onto any retry of it."""
        return {"config_snapshot": self.config_snapshot, "raw_retention": self.raw_retention}


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
        help_text="Populated once this input's copy to the raw bucket has been verified (size+hash), "
                   "even if the source delete is still pending.")
    source_handled_at = models.DateTimeField(
        blank=True, null=True,
        help_text="When the source was moved to the raw bucket, or deleted under \"delete\" Raw Retention.")
    source_status = models.CharField(
        max_length=25, choices=ETL_JOB_INPUT_SOURCE_STATUS_CHOICES, default=ETL_JOB_INPUT_SOURCE_STATUS_PENDING,
        blank=False, null=False, db_index=True)
    cleanup_attempts = models.PositiveIntegerField(
        default=0, help_text="Number of source-delete attempts made so far (capped backoff).")
    cleanup_next_attempt_at = models.DateTimeField(
        blank=True, null=True, help_text="When the next capped-backoff cleanup retry is due.")

    class Meta:
        db_table = "mires_etl_job_input"
        ordering = ["job", "bucket", "key"]

    def __str__(self):
        return f"{self.bucket}/{self.key}"

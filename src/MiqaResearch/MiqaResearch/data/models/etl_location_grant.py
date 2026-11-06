from uuid import uuid7

from django.db import models

from .etl_storage import EtlStorage, default_storage_id
from .research_project import ResearchProject


class EtlLocationGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name="etl_location_grants",
        blank=False, null=False, db_index=True)
    storage = models.ForeignKey(
        EtlStorage, on_delete=models.PROTECT, related_name="location_grants", blank=False, null=False,
        default=default_storage_id)
    bucket = models.CharField(max_length=200, blank=False, null=False)
    prefix = models.CharField(
        max_length=500, blank=True, default="", help_text="Empty grants access to the whole bucket.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_location_grant"
        ordering = ["project", "bucket", "prefix"]
        unique_together = [("project", "storage", "bucket", "prefix")]

    def __str__(self):
        return f"{self.project} -> {self.storage}:{self.bucket}/{self.prefix}"

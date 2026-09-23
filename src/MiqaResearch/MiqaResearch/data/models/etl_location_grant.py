from uuid import uuid7

from django.db import models

from .research_project import ResearchProject


class EtlLocationGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name="etl_location_grants",
        blank=False, null=False, db_index=True)
    bucket = models.CharField(max_length=200, blank=False, null=False)
    prefix = models.CharField(
        max_length=500, blank=True, default="", help_text="Empty grants access to the whole bucket.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_location_grant"
        ordering = ["project", "bucket", "prefix"]
        unique_together = [("project", "bucket", "prefix")]

    def __str__(self):
        return f"{self.project} -> {self.bucket}/{self.prefix}"

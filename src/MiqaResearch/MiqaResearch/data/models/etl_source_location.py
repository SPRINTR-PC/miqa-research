from uuid import uuid7

from django.db import models

from .research_project import ResearchProject


class EtlSourceLocation(models.Model):
    """A named bucket/prefix a project's Pipeline Bindings read from (#268). Always inside one of the
    project's `EtlLocationGrant`s; bucket/prefix are fixed once created, only the name changes."""
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name="etl_source_locations",
        blank=False, null=False, db_index=True)
    name = models.CharField(max_length=100, blank=False, null=False)
    bucket = models.CharField(max_length=200, blank=False, null=False)
    prefix = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_source_location"
        ordering = ["project", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="mires_etl_source_location_project_name"),
            models.UniqueConstraint(
                fields=["project", "bucket", "prefix"], name="mires_etl_source_location_project_bucket_prefix"),
        ]

    def __str__(self):
        return f"{self.name} ({self.bucket}/{self.prefix})"

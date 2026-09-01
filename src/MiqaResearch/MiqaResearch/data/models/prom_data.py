from uuid import uuid7

from django.contrib.auth import get_user_model
from django.db import models
from kpforms.models import FormTemplate

from .research_project import ResearchProject

User = get_user_model()


class PromFormTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False, unique=True)
    template = models.ForeignKey(FormTemplate, on_delete=models.PROTECT, blank=False, null=False)
    project_specific = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, blank=True, null=True)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "mires_prom_form_template"
        ordering = ["name", "-created_at", ]
        unique_together = [("name", "project_specific")]
        indexes = [
            models.Index(fields=["published"], name="idx_prom_form_template_pub"),
            models.Index(fields=["name", "created_at",], name="idx_prom_form_template_ver")
        ]

    def __str__(self) -> str:
        return f"{self.name} {'' if self.published else ''} {self.updated_at:Y-m-d H:i:s}"


def upload_to(instance, filename):
    file_extension = "" if "." not in filename else "." + filename.split('.')[-1]
    output_path = f"{instance.project.id}/PROM/{instance.id}{file_extension}"
    return output_path


class PromData(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(ResearchProject, on_delete=models.PROTECT, blank=False, null=False, db_index=True)
    prom_form_template = models.ForeignKey(PromFormTemplate, on_delete=models.PROTECT, blank=False, null=False, db_index=True)
    prom_form_file = models.FileField(upload_to=upload_to, blank=False, null=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=False, null=False, db_index=True)

    class Meta:
        db_table = "mires_prom_data"
        ordering = ["-uploaded_at"]


class ParsedPromForm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    data = models.JSONField(blank=False, null=False)
    prom_file = models.ForeignKey(PromData, on_delete=models.PROTECT, blank=False, null=False, db_index=True)
    validated_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, db_index=True)
    validated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "mires_parsed_prom_form"
        ordering = ["-validated_at"]

    def __str__(self) -> str:
        return f"ParsedPromForm {self.id} validated at {self.validated_at} by {self.validated_by}"

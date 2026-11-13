from uuid import uuid7

from django.core.exceptions import ValidationError
from django.db import models

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CHOICES

from .etl_project_settings import get_max_script_source_bytes
from .etl_script_storage import EtlScriptStorage
from .research_project import ResearchProject


def etl_script_version_upload_to(instance, filename):
    return f"ETL_SCRIPTS/{instance.script_id}/{instance.version}/{filename}"


class EtlScriptQuerySet(models.QuerySet):
    def delete(self):
        # Instance.delete() (below) only catches a direct instance delete --
        # Django's bulk queryset delete bypasses it entirely and needs its
        # own guard to keep "archive-only, no hard delete" actually true.
        raise ValidationError("EtlScript records are archive-only and cannot be hard-deleted; set archived_at instead.")


class EtlScript(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False)
    description = models.TextField(blank=True, default="")
    origin = models.CharField(
        max_length=10, choices=ETL_SCRIPT_ORIGIN_CHOICES, blank=False, null=False,
        help_text="Native scripts are global and read-only; custom scripts are project-owned.")
    project = models.ForeignKey(
        # PROTECT, not CASCADE: a project delete must not be able to sneak
        # its EtlScripts past the "no hard delete" rule enforced below.
        ResearchProject, on_delete=models.PROTECT, related_name="etl_scripts", blank=True, null=True,
        help_text="Owning project for a custom script; null for a native (global) script.")
    datatype_name = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Name of the registered ETL Datatype (MiqaResearch.etl_datatypes) this script's "
                   "output rows conform to. Stable across the script's versions.")
    archived_at = models.DateTimeField(
        blank=True, null=True, help_text="Scripts are archived, never hard-deleted.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EtlScriptQuerySet.as_manager()

    class Meta:
        db_table = "mires_etl_script"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        raise ValidationError("EtlScript records are archive-only and cannot be hard-deleted; set archived_at instead.")

    def hard_delete(self):
        """Bypasses the archive-only guard. Only `actions.etl.scripts.delete_archived_script` may call
        this, after it has checked the Script is archived and unused."""
        return super().delete()


class EtlScriptVersionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        # save() (below) only catches a direct instance update -- Django's
        # bulk queryset update bypasses it entirely and needs its own guard
        # to keep "immutable ... no update path" actually true.
        raise ValidationError("EtlScriptVersion is immutable and cannot be updated after creation.")


class EtlScriptVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    script = models.ForeignKey(
        EtlScript, on_delete=models.CASCADE, related_name="versions", blank=False, null=False, db_index=True)
    version = models.PositiveIntegerField(blank=False, null=False)
    source = models.FileField(
        upload_to=etl_script_version_upload_to, storage=EtlScriptStorage(), blank=False, null=False)
    sha256 = models.CharField(max_length=64, blank=False, null=False, help_text="SHA-256 hex of the source file bytes.")
    image_key = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Sandbox image key (language + runtime + release) this Version's source is written "
                   "against; resolved through the platform's image allowlist at run time.")
    config_schema = models.JSONField(
        blank=True, null=True,
        help_text="Optional JSON Schema a Binding's config must satisfy to pin this Version (#238); "
                   "null keeps config free-form.")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EtlScriptVersionQuerySet.as_manager()

    class Meta:
        db_table = "mires_etl_script_version"
        ordering = ["script", "-version"]
        unique_together = [("script", "version")]

    def __str__(self):
        return f"{self.script} v{self.version}"

    def save(self, *args, **kwargs):
        # Pinned by PipelineBinding and recorded on every EtlJob -- a Job's
        # provenance must always reflect exactly what ran, so a version, once
        # created, can never be edited in place.
        if not self._state.adding:
            raise ValidationError("EtlScriptVersion is immutable and cannot be updated after creation.")
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # The size cap is a per-project setting (with a global default), not
        # a fixed constant -- so, unlike a plain field validator, it needs
        # self.script.project and can only be checked here.
        if self.source and self.script_id:
            max_bytes = get_max_script_source_bytes(self.script.project)
            if self.source.size > max_bytes:
                raise ValidationError({"source": f"Script source must be at most {max_bytes} bytes for this project."})

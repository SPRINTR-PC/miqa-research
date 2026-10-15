from uuid import uuid7

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from oauth2_provider.settings import oauth2_settings

from .clinic import Clinic
from .research_project import ResearchProject


class ClientBinding(models.Model):
    """The tie between a client-credentials Application and one Research Project, optionally one Site
    (ADR 0027). On WADO the client sees participants as a role with that Site would (no Site: all Sites);
    an Application without a binding sees no participant data. The project never changes; the binding
    belongs to the project, not to whoever issued it (`issued_by` is informational only)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    application = models.OneToOneField(
        oauth2_settings.APPLICATION_MODEL, on_delete=models.CASCADE, related_name="client_binding")
    research_project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name="client_bindings", db_index=True)
    clinic = models.ForeignKey(
        Clinic, on_delete=models.PROTECT, null=True, blank=True, related_name="client_bindings",
        help_text="The Site this client is narrowed to; empty means all Sites of the project.")
    dicom_raw = models.BooleanField(
        default=False,
        help_text="Granted the `dicom:raw` scope: the raw-bytes WADO endpoints (original files, full PHI).")
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_client_binding"
        ordering = ["research_project", "created_at"]

    def __str__(self):
        return f"{self.application} -> {self.research_project}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            stored = type(self).objects.filter(pk=self.pk).values_list("research_project_id", flat=True).first()
            if stored is not None and stored != self.research_project_id:
                raise ValidationError("A Client Binding's Research Project can't be changed.")
        super().save(*args, **kwargs)

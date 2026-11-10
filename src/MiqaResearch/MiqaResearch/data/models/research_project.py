from uuid import uuid7

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models

from contract.constants.research_project_role import PROJECT_ROLE_SITE_PI
from helpers.db_fields import EncryptedCharField

from .clinic import Clinic

User = get_user_model()


class ResearchProject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False, unique=True)
    description = models.TextField(blank=False, null=False)
    dicom_duplicate_handling = models.CharField(
        max_length=10, choices=[("skip", "Skip"), ("update", "Update")], default="skip", blank=False, null=False,
        help_text="Default behavior when DICOM ingestion encounters a file whose SOP Instance UID already exists")
    dicom_delete_originals_after_storage = models.BooleanField(
        blank=True,
        null=True,
        default=None,
        help_text=(
            "Overrides MIRES_DICOM_DELETE_ORIGINALS_AFTER_STORAGE for this project; "
            "null defers to the global setting"
        ),
    )
    dicom_hashuid_salt_key = EncryptedCharField(
        blank=True, null=True,
        help_text="Salt used to pseudonymize incoming DICOM UIDs (CTP-style HashUID) for this project. "
                   "Auto-generated once on first use; must never be rotated, or already-ingested UIDs stop matching.")
    blinded_annotation = models.BooleanField(
        default=False,
        help_text="Blinded Annotation (ADR 0026): every user sees only their own Annotations and Segmentations, "
                  "ingested ones are hidden, and bound machine clients get none. Set by a PI or Project Admin.")
    blinding_epoch = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Bumped on every Blinded Annotation change; "
            "a Blinding Reveal counts only in the epoch it was made in."
        ),
    )

    class Meta:
        db_table = "mires_research_project"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ResearchProjectRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False, unique=True)
    description = models.TextField(blank=False, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "mires_research_project_role"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ResearchProjectClinicMap(models.Model):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, blank=False, null=False, db_index=True)

    class Meta:
        db_table = "mires_research_project_clinic_map"
        unique_together = [("project", "clinic")]
        ordering = ["project", "clinic"]
        indexes = [
            models.Index(fields=["project", "clinic"], name="idx_project_clinic_map"),
            models.Index(fields=["clinic", "project"], name="idx_clinic_project_map"),
        ]

    def __str__(self):
        return f"{self.project} - {self.clinic}"


class ResearchProjectUserRoleMap(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    role = models.ForeignKey(ResearchProjectRole, on_delete=models.CASCADE, blank=False, null=False, db_index=True)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        db_table = "mires_research_project_user_role_map"
        unique_together = [("user", "project", "role")]
        ordering = ["project", "user", "role"]
        indexes = [
            models.Index(fields=["project", "user", "role"], name="idx_project_user_role_map"),
            models.Index(fields=["user", "project", "role"], name="idx_user_project_role_map"),
            models.Index(fields=["project", "role", "user"], name="idx_project_role_user_map"),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.project} - {self.role}"

    def save(self, *args, **kwargs):
        # Enforced on save too, not only in forms/admin: a Site PI without a clinic would be
        # all-Sites under Participant Visibility, which is exactly what the role must not be.
        self._validate_site_pi_clinic()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self._validate_site_pi_clinic()

    def _validate_site_pi_clinic(self):
        if self.role_id and self.clinic_id is None and self.role.name == PROJECT_ROLE_SITE_PI:
            raise ValidationError({"clinic": "A Site PI must be assigned a clinic (Site)."})

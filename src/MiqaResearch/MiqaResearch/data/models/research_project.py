from uuid import uuid7

from django.contrib.auth import get_user_model
from django.db import models

from .clinic import Clinic

User = get_user_model()


class ResearchProject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False, unique=True)
    description = models.TextField(blank=False, null=False)

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

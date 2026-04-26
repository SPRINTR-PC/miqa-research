from uuid import uuid7

from django.db import models

from .research_project import ResearchProject


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    patient_id = models.CharField(max_length=100, blank=False, null=False, unique=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], blank=False, null=False)
    research_project = models.ForeignKey(ResearchProject, on_delete=models.PROTECT, blank=False, null=False, db_index=True)

    class Meta:
        db_table = "mires_patient"
        ordering = ["last_name", "first_name"]
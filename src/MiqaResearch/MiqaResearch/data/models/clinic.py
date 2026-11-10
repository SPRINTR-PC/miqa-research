from uuid import uuid7

from django.db import models


class Clinic(models.Model):
    id = models.UUIDField(default=uuid7, primary_key=True, editable=False)
    clinic_code = models.CharField(
        max_length=100, unique=True, blank=False, null=False, help_text="Unique code for the clinic"
    )
    clinic_name = models.CharField(max_length=60, blank=False, null=False, help_text="Name of the clinic")

    class Meta:
        db_table = "mires_clinic"

    def __str__(self):
        return f"{self.clinic_name} ({self.clinic_code})"

from uuid import uuid7

from django.db import models


class Clinic(models.Model):
    id = models.UUIDField(default=uuid7, primary_key=True, editable=False)
    clinic_name = models.CharField(max_length=255, blank=False, null=False, help_text="Name of the clinic")

    class Meta:
        db_table = "mires_clinic"
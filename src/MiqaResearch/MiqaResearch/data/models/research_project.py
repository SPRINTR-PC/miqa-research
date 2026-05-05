from uuid import uuid7

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class ResearchProject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False, unique=True)
    description = models.TextField(blank=False, null=False)
    primary_investigator = models.ForeignKey(User, on_delete=models.PROTECT, blank=False, null=False, db_index=True)

    class Meta:
        db_table = "mires_research_project"
        ordering = ["name"]

    def __str__(self):
        return self.name
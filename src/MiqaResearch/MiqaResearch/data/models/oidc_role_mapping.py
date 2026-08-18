import json
import os
from uuid import uuid7

from django.contrib.auth.models import Group
from django.db import models


class OIDCRoleMappingManager(models.Manager):
    def seed_from_env(self, only_if_empty: bool = False) -> int:
        if only_if_empty and self.exists():
            return 0

        role_mapping = json.loads(os.getenv("MIRES_OIDC_ROLE_MAPPING", "{}"))
        seeded = 0
        for oidc_role, group_name in role_mapping.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            self.update_or_create(oidc_role=oidc_role, defaults={"group": group})
            seeded += 1
        return seeded


class OIDCRoleMapping(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    oidc_role = models.CharField(max_length=200, unique=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="oidc_role_mappings")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OIDCRoleMappingManager()

    class Meta:
        db_table = "mires_oidc_role_mapping"
        ordering = ["oidc_role"]

    def __str__(self):
        return f"{self.oidc_role} -> {self.group.name}"

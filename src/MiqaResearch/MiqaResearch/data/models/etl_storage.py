import os
from uuid import uuid7

from django.db import models

from contract.constants.etl import ETL_STORAGE_KIND_CHOICES, ETL_STORAGE_KIND_S3


class EtlStorage(models.Model):
    """A Connected Storage (#394): an S3-compatible store ETL reads from. Holds only the *names* of
    the env vars carrying its credential, never a secret value. The Default storage is the
    platform-wide MIRES_ETL_S3_* settings, read live."""
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=10, choices=ETL_STORAGE_KIND_CHOICES, default=ETL_STORAGE_KIND_S3)
    endpoint_url = models.CharField(max_length=500, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    access_key_id_env = models.CharField(max_length=100, blank=True, default="")
    secret_access_key_env = models.CharField(max_length=100, blank=True, default="")
    is_default = models.BooleanField(default=False, editable=False)
    managed_by_settings = models.BooleanField(
        default=False, editable=False, help_text="Declared in MIRES_ETL_STORAGES; read-only in the admin.")
    no_longer_in_settings = models.BooleanField(
        default=False, editable=False,
        help_text="Was declared in MIRES_ETL_STORAGES but removed while still referenced.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_etl_storage"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def credentials_configured(self) -> bool:
        if self.is_default:
            return True
        return bool(os.environ.get(self.access_key_id_env) and os.environ.get(self.secret_access_key_env))


def default_storage() -> EtlStorage:
    """The Default storage (created on demand if missing)."""
    return EtlStorage.objects.get_or_create(is_default=True, defaults={"name": "Default"})[0]


def default_storage_id():
    """The FK default for rows that name no storage."""
    return default_storage().pk

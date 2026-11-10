import os
from uuid import uuid7

from django.conf import settings
from django.db import models

from contract.constants.etl import ETL_STORAGE_KIND_CHOICES, ETL_STORAGE_KIND_S3
from helpers import vault


class EtlStorage(models.Model):
    """A Connected Storage (#394): an S3-compatible store ETL reads from. Holds only the *names* of
    the env vars and/or Vault path + key carrying its credential (#396), never a secret value.
    Per credential an env var, when set, wins over Vault. The Default storage is the
    platform-wide MIRES_ETL_S3_* settings, read live."""
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=10, choices=ETL_STORAGE_KIND_CHOICES, default=ETL_STORAGE_KIND_S3)
    endpoint_url = models.CharField(max_length=500, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    access_key_id_env = models.CharField(max_length=100, blank=True, default="")
    secret_access_key_env = models.CharField(max_length=100, blank=True, default="")
    access_key_id_vault_path = models.CharField(max_length=200, blank=True, default="")
    access_key_id_vault_key = models.CharField(max_length=100, blank=True, default="")
    secret_access_key_vault_path = models.CharField(max_length=200, blank=True, default="")
    secret_access_key_vault_key = models.CharField(max_length=100, blank=True, default="")
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

    def resolve_credentials(self) -> tuple[str, str] | None:
        """(access key id, secret) or None. Each credential: its env var if set, else its Vault
        secret (read live; Vault off, unreachable or unseeded counts as unset)."""
        access_key_id = self._resolve(self.access_key_id_env, self.access_key_id_vault_path,
                                      self.access_key_id_vault_key)
        secret = self._resolve(self.secret_access_key_env, self.secret_access_key_vault_path,
                               self.secret_access_key_vault_key)
        return (access_key_id, secret) if access_key_id and secret else None

    @staticmethod
    def _resolve(env_name: str, vault_path: str, vault_key: str) -> str | None:
        value = os.environ.get(env_name) if env_name else None
        if value or not (vault_path and vault_key and settings.USE_VAULT):
            return value or None
        try:
            client = vault.get_vault_client(url=settings.VAULT_URL, token=settings.VAULT_TOKEN)
            return vault.get_vault_secret(client, vault_path, vault_key) or None
        except Exception:
            return None

    @property
    def credentials_configured(self) -> bool:
        if self.is_default:
            return True
        return self.resolve_credentials() is not None


def default_storage() -> EtlStorage:
    """The Default storage (created on demand if missing)."""
    return EtlStorage.objects.get_or_create(is_default=True, defaults={"name": "Default"})[0]


def default_storage_id():
    """The FK default for rows that name no storage."""
    return default_storage().pk

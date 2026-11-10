"""Connected Storages declared in MIRES_ETL_STORAGES (#394), mirrored into the database like native
scripts (#226). A declared storage is created or updated and marked settings-managed. One that
disappears from settings is deleted only if no grant, Source Location or Binding references it,
otherwise kept and flagged `no_longer_in_settings`. The Default storage and storages created in
the admin are never touched."""
import logging

from asgiref.sync import sync_to_async
from django.conf import settings

from contract.constants.audit_log import EVENT_TYPE_ETL_STORAGE_BROWSED
from contract.constants.etl import ETL_STORAGE_KIND_S3
from MiqaResearch.data.models import EtlStorage
from MiqaResearch.readers.etl_storage_browser import StorageListing, list_buckets, list_folder

from .audit import record_etl_event

logger = logging.getLogger(__name__)

_FIELDS = ("kind", "endpoint_url", "region", "access_key_id_env", "secret_access_key_env",
           "access_key_id_vault_path", "access_key_id_vault_key",
           "secret_access_key_vault_path", "secret_access_key_vault_key")


def sync_etl_storages() -> None:
    declared = {entry["name"]: entry for entry in settings.ETL_STORAGES}
    for name, entry in declared.items():
        _upsert(name, entry)

    for storage in EtlStorage.objects.filter(managed_by_settings=True).exclude(name__in=declared):
        if _is_referenced(storage):
            if not storage.no_longer_in_settings:
                storage.no_longer_in_settings = True
                storage.save(update_fields=["no_longer_in_settings"])
        else:
            storage.delete()


def _upsert(name: str, entry: dict) -> None:
    values = {field: entry.get(field, "") for field in _FIELDS}
    values["kind"] = values["kind"] or ETL_STORAGE_KIND_S3
    existing = EtlStorage.objects.filter(name=name).first()
    if existing is not None and not existing.managed_by_settings:
        logger.error("MIRES_ETL_STORAGES: %r clashes with a storage not managed by settings; skipped.", name)
        return
    EtlStorage.objects.update_or_create(
        name=name, defaults={**values, "managed_by_settings": True, "no_longer_in_settings": False})


def _is_referenced(storage: EtlStorage) -> bool:
    return (storage.location_grants.exists() or storage.source_locations.exists()
            or storage.pipeline_bindings.exists())


async def browse_storage(*, user, request, project, storage, bucket=None, prefix="") -> StorageListing:
    """One read-only browse step (#394): the storage's buckets (`bucket` None) or one folder level
    of a bucket. Audited before the call, so a denied or failed attempt shows too. The entry names
    the storage and bucket only -- never the prefix or any object name."""
    metadata = {"etl_storage_id": str(storage.id)}
    if bucket:
        metadata["bucket"] = bucket
    await record_etl_event(
        EVENT_TYPE_ETL_STORAGE_BROWSED, user=user, request=request, project=project, metadata=metadata)
    if bucket:
        return await sync_to_async(list_folder)(storage, bucket, prefix)
    return await sync_to_async(list_buckets)(storage)

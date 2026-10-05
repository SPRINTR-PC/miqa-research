"""Mirrors the codebase's native ETL Scripts into the database (#226). A native Script is keyed
by its name; its Versions stay immutable, so a changed source publishes a new Version and every
Binding keeps the Version it pinned until a manager re-pins it.
"""
import hashlib

from django.core.files.base import ContentFile
from django.utils import timezone

from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch import etl_native_scripts
from MiqaResearch.data.models import EtlScript, EtlScriptVersion
from MiqaResearch.etl_config_schema import parse_config_schema
from MiqaResearch.etl_sandbox.images import image_key_for_script_filename


def sync_native_etl_scripts() -> None:
    # Archive, never delete: Bindings and past Jobs may still reference a dropped Script's Versions.
    shipped_names = [native.name for native in etl_native_scripts.NATIVE_SCRIPTS]
    EtlScript.objects.filter(origin=ETL_SCRIPT_ORIGIN_NATIVE, archived_at__isnull=True) \
        .exclude(name__in=shipped_names).update(archived_at=timezone.now())

    for native in etl_native_scripts.NATIVE_SCRIPTS:
        source = etl_native_scripts.native_script_path(native.filename).read_bytes()
        script, _ = EtlScript.objects.update_or_create(
            origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None, name=native.name,
            defaults={"datatype_name": native.datatype_name, "description": native.description, "archived_at": None},
        )
        config_schema = _sidecar_config_schema(native.filename)
        sha256 = hashlib.sha256(source).hexdigest()
        latest = script.versions.order_by("-version").first()
        if latest is not None and latest.sha256 == sha256 and latest.config_schema == config_schema:
            continue
        EtlScriptVersion.objects.create(
            script=script, version=(latest.version + 1) if latest else 1,
            source=ContentFile(source, name=native.filename), sha256=sha256,
            image_key=image_key_for_script_filename(native.filename), config_schema=config_schema)


def _sidecar_config_schema(filename: str) -> dict | None:
    """#238: a native Script's config schema lives next to it as `<stem>.schema.json`. A malformed one
    raises `ConfigSchemaInvalid` rather than publishing a Version no config could be checked against."""
    sidecar = etl_native_scripts.native_script_path(filename).with_suffix(".schema.json")
    return parse_config_schema(sidecar.read_bytes()) if sidecar.exists() else None

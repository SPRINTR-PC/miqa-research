"""Writes for the ETL Scripts section (#158): create/edit/archive a custom Script, add a Version.
Callers must pre-validate input (see `MiqaResearch.interfaces.http.forms.etl`) -- these functions
assume `name`/`description`/`source` are already well-formed (including `source`'s extension
naming a supported language, which picks the Version's sandbox `image_key`, #166) and only enforce the business rules
that need a DB round trip: the Script's project/origin/archived state.
"""
from django.db.models import Max
from django.utils import timezone

from contract.constants.audit_log import (
    EVENT_TYPE_ETL_SCRIPT_ARCHIVED,
    EVENT_TYPE_ETL_SCRIPT_CREATED,
    EVENT_TYPE_ETL_SCRIPT_UPDATED,
    EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED,
)
from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import EtlScript, EtlScriptVersion, ResearchProject
from MiqaResearch.etl_sandbox.images import image_key_for_script_filename

from ._hashing import sha256_of_upload
from .audit import record_etl_event
from .exceptions import EtlScriptStateError


def _require_manageable_custom_script(script: EtlScript, project: ResearchProject) -> None:
    if script.origin != ETL_SCRIPT_ORIGIN_CUSTOM or script.project_id != project.id:
        raise EtlScriptStateError("Only this project's own custom Scripts can be managed here.")
    if script.archived_at is not None:
        raise EtlScriptStateError("This Script is archived and can no longer be edited.")


async def create_custom_script(*, project, user, request, name, description, datatype_name, source) -> EtlScript:
    script = await EtlScript.objects.acreate(
        name=name, description=description, origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project,
        datatype_name=datatype_name)
    await EtlScriptVersion.objects.acreate(
        script=script, version=1, source=source, sha256=sha256_of_upload(source),
        image_key=image_key_for_script_filename(source.name))
    await record_etl_event(
        EVENT_TYPE_ETL_SCRIPT_CREATED, user=user, request=request, project=project,
        metadata={"etl_script_id": str(script.id), "datatype": datatype_name})
    return script


async def update_custom_script(*, project, user, request, script, name, description, datatype_name="") -> EtlScript:
    _require_manageable_custom_script(script, project)
    script.name = name
    script.description = description
    # Set once (#223): Bindings and past Jobs depend on it. Only a Script left without one -- created
    # before the Datatype was chosen at creation -- may have it filled in here.
    if datatype_name and not script.datatype_name:
        script.datatype_name = datatype_name
    await script.asave(update_fields=["name", "description", "datatype_name", "updated_at"])
    await record_etl_event(
        EVENT_TYPE_ETL_SCRIPT_UPDATED, user=user, request=request, project=project,
        metadata={"etl_script_id": str(script.id)})
    return script


async def create_script_version(*, project, user, request, script, source) -> EtlScriptVersion:
    _require_manageable_custom_script(script, project)
    latest = await script.versions.aaggregate(latest_version=Max("version"))
    next_version = (latest["latest_version"] or 0) + 1
    version = await EtlScriptVersion.objects.acreate(
        script=script, version=next_version, source=source, sha256=sha256_of_upload(source),
        image_key=image_key_for_script_filename(source.name))
    await record_etl_event(
        EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED, user=user, request=request, project=project,
        metadata={"etl_script_id": str(script.id), "etl_script_version_id": str(version.id)})
    return version


async def archive_custom_script(*, project, user, request, script) -> EtlScript:
    _require_manageable_custom_script(script, project)
    script.archived_at = timezone.now()
    await script.asave(update_fields=["archived_at", "updated_at"])
    await record_etl_event(
        EVENT_TYPE_ETL_SCRIPT_ARCHIVED, user=user, request=request, project=project,
        metadata={"etl_script_id": str(script.id)})
    return script

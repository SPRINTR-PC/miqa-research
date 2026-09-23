"""Writes for the ETL Bindings section (#158): create a PipelineBinding through the wizard.
Callers must pre-validate input (see `MiqaResearch.interfaces.http.forms.etl`), including that the
source bucket/prefix falls within one of the project's `EtlLocationGrant`s -- this module only
re-checks the parts that need a DB round trip: that the chosen Script Version is still usable for
this project, and that no other Binding already claims the same source bucket/prefix.
"""
from contract.constants.audit_log import EVENT_TYPE_ETL_BINDING_CREATED
from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import EtlScriptVersion, PipelineBinding

from .audit import record_etl_event
from .exceptions import EtlBindingConflict, EtlScriptVersionNotUsable


async def create_pipeline_binding(
        *, project, user, request, source_bucket, source_prefix, script_version_id, raw_bucket, raw_prefix,
        timeout_seconds_override=None, memory_mb_override=None, cpu_millicores_override=None) -> PipelineBinding:
    try:
        script_version = await EtlScriptVersion.objects.select_related("script").aget(id=script_version_id)
    except EtlScriptVersion.DoesNotExist:
        raise EtlScriptVersionNotUsable("The chosen Script Version no longer exists.")

    script = script_version.script
    is_own_or_native = script.origin == ETL_SCRIPT_ORIGIN_NATIVE or script.project_id == project.id
    if script.archived_at is not None or not is_own_or_native:
        raise EtlScriptVersionNotUsable("The chosen Script Version is no longer usable for this project.")

    already_bound = await PipelineBinding.objects.filter(
        source_bucket=source_bucket, source_prefix=source_prefix).aexists()
    if already_bound:
        raise EtlBindingConflict("A Binding for that source bucket/prefix already exists.")

    binding = await PipelineBinding.objects.acreate(
        project=project, source_bucket=source_bucket, source_prefix=source_prefix,
        script_version=script_version, raw_bucket=raw_bucket, raw_prefix=raw_prefix,
        timeout_seconds_override=timeout_seconds_override, memory_mb_override=memory_mb_override,
        cpu_millicores_override=cpu_millicores_override,
    )

    await record_etl_event(
        EVENT_TYPE_ETL_BINDING_CREATED, user=user, request=request, project=project,
        metadata={"etl_pipeline_binding_id": str(binding.id)})
    return binding

"""Writes for the ETL Bindings section (#158, #224): create a PipelineBinding through the wizard,
or edit one. Callers must pre-validate input (see `MiqaResearch.interfaces.http.forms.etl`),
including that the source and (under "move" Raw Retention) raw bucket/prefix fall within the
project's `EtlLocationGrant`s, and that only an Admin switches a Binding into "delete" --
this module only re-checks the parts that need a DB round trip: that the chosen Script Version is
still usable for this project, that the config satisfies its config schema (#238), and that no
other Binding already claims the same source bucket/prefix.

An edit never touches the source bucket/prefix: it is the Binding's identity (the processed-file
ledger is keyed on it). A Job already queued keeps its own Script Version, config and Raw
Retention snapshot. Under "delete" Raw Retention the raw bucket/prefix are blank (#246).
"""
from asgiref.sync import sync_to_async

from contract.constants.audit_log import EVENT_TYPE_ETL_BINDING_CREATED, EVENT_TYPE_ETL_BINDING_UPDATED
from contract.constants.etl import (
    ETL_SCRIPT_ORIGIN_NATIVE,
    PIPELINE_BINDING_GROUPING_FILE,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
)
from MiqaResearch.data.models import EtlScriptVersion, PipelineBinding
from MiqaResearch.etl_config_schema import ConfigSchema

from .audit import record_etl_event
from .exceptions import (
    EtlBindingConfigInvalid,
    EtlBindingConflict,
    EtlScriptVersionNotUsable,
    EtlSourceLocationNotInProject,
)


async def create_pipeline_binding(
        *, project, user, request, source_location, script_version_id, raw_bucket, raw_prefix,
        raw_retention=PIPELINE_BINDING_RAW_RETENTION_MOVE, grouping_mode=PIPELINE_BINDING_GROUPING_FILE,
        quiescence_seconds=None, config=None,
        timeout_seconds_override=None, memory_mb_override=None, cpu_millicores_override=None) -> PipelineBinding:
    # The Binding copies its Source Location's bucket/prefix (#268); those never change afterwards.
    if source_location.project_id != project.id:
        raise EtlSourceLocationNotInProject("That Source Location belongs to another project.")
    source_bucket, source_prefix = source_location.bucket, source_location.prefix
    script_version = await _usable_script_version(project, script_version_id)
    _require_config_fits(script_version, config or {})

    already_bound = await PipelineBinding.objects.filter(
        storage_id=source_location.storage_id, source_bucket=source_bucket, source_prefix=source_prefix).aexists()
    if already_bound:
        raise EtlBindingConflict("A Binding for that source bucket/prefix already exists.")

    binding = await PipelineBinding.objects.acreate(
        project=project, storage_id=source_location.storage_id, source_bucket=source_bucket,
        source_prefix=source_prefix, source_location=source_location,
        script_version=script_version, raw_retention=raw_retention, raw_bucket=raw_bucket, raw_prefix=raw_prefix,
        grouping_mode=grouping_mode, **_quiescence_kwargs(quiescence_seconds), config=config or {},
        timeout_seconds_override=timeout_seconds_override, memory_mb_override=memory_mb_override,
        cpu_millicores_override=cpu_millicores_override,
    )

    await record_etl_event(
        EVENT_TYPE_ETL_BINDING_CREATED, user=user, request=request, project=project,
        metadata={"etl_pipeline_binding_id": str(binding.id), "raw_retention": binding.raw_retention})
    return binding


async def update_pipeline_binding(
        *, project, user, request, binding, script_version_id, raw_bucket, raw_prefix,
        grouping_mode, raw_retention, quiescence_seconds=None, config=None,
        timeout_seconds_override=None, memory_mb_override=None, cpu_millicores_override=None) -> PipelineBinding:
    script_version = await _usable_script_version(project, script_version_id)
    _require_config_fits(script_version, config or {})

    grouping_changed = grouping_mode != binding.grouping_mode
    raw_retention_previous = binding.raw_retention
    binding.raw_retention = raw_retention
    binding.script_version = script_version
    binding.raw_bucket = raw_bucket
    binding.raw_prefix = raw_prefix
    binding.grouping_mode = grouping_mode
    if quiescence_seconds is not None:
        binding.quiescence_seconds = quiescence_seconds
    binding.config = config or {}
    binding.timeout_seconds_override = timeout_seconds_override
    binding.memory_mb_override = memory_mb_override
    binding.cpu_millicores_override = cpu_millicores_override
    await binding.asave()
    if grouping_changed:
        from MiqaResearch.tasks.etl_orchestrator.polling import rehome_backlog_after_grouping_change
        await sync_to_async(rehome_backlog_after_grouping_change)(binding)

    await record_etl_event(
        EVENT_TYPE_ETL_BINDING_UPDATED, user=user, request=request, project=project,
        metadata={
            "etl_pipeline_binding_id": str(binding.id),
            "raw_retention": binding.raw_retention, "raw_retention_previous": raw_retention_previous,
        })
    return binding


async def _usable_script_version(project, script_version_id) -> EtlScriptVersion:
    try:
        script_version = await EtlScriptVersion.objects.select_related("script").aget(id=script_version_id)
    except EtlScriptVersion.DoesNotExist:
        raise EtlScriptVersionNotUsable("The chosen Script Version no longer exists.")

    script = script_version.script
    is_own_or_native = script.origin == ETL_SCRIPT_ORIGIN_NATIVE or script.project_id == project.id
    if script.archived_at is not None or not is_own_or_native:
        raise EtlScriptVersionNotUsable("The chosen Script Version is no longer usable for this project.")
    return script_version


def _require_config_fits(script_version: EtlScriptVersion, config: dict) -> None:
    if script_version.config_schema is None:
        return
    errors = ConfigSchema(script_version.config_schema).errors(config)
    if errors:
        raise EtlBindingConfigInvalid(" ".join(error.message for error in errors))


def _quiescence_kwargs(quiescence_seconds) -> dict:
    """Blank means "use the model's default window" rather than storing a null the poller can't use."""
    return {} if quiescence_seconds is None else {"quiescence_seconds": quiescence_seconds}

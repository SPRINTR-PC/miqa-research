from contract.constants.audit_log import EVENT_TYPE_ETL_SETTINGS_UPDATED
from MiqaResearch.data.models import EtlProjectSettings

from .audit import record_etl_event


async def update_etl_project_settings(
        *, project, user, request, log_retention_days=None, max_script_source_bytes=None) -> EtlProjectSettings:
    settings_obj, _ = await EtlProjectSettings.objects.aupdate_or_create(
        project=project,
        defaults={"log_retention_days": log_retention_days, "max_script_source_bytes": max_script_source_bytes},
    )
    await record_etl_event(
        EVENT_TYPE_ETL_SETTINGS_UPDATED, user=user, request=request, project=project,
        metadata={"etl_project_settings_id": str(settings_obj.id)})
    return settings_obj

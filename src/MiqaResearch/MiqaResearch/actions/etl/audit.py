from asgiref.sync import sync_to_async

from MiqaResearch.data.models import AuditLog


async def record_etl_event(event_type, *, user, request, project, metadata=None):
    """Records an ETL manage-action AuditLog entry. Metadata carries only identifiers (e.g. which
    Script/Binding was touched), never field values such as a name, description or bucket path --
    the audit trail must show *that* an action happened, not the data involved."""
    await sync_to_async(AuditLog.objects.record)(
        event_type, user=user, request=request, project=project, metadata=metadata or {})

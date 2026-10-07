"""Source Locations and location grants (#268). Grants are the per-project isolation boundary for
the one platform-wide ETL credential; a Source Location is a named bucket/prefix inside a grant
that the Binding wizard offers. Callers check who may act (`EtlPermissions`); these enforce the
data rules: locations stay inside grants, bucket/prefix never change, nothing in use is deleted.
"""
from contract.constants.audit_log import (
    EVENT_TYPE_ETL_LOCATION_GRANT_CREATED,
    EVENT_TYPE_ETL_LOCATION_GRANT_DELETED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_CREATED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_DELETED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_RENAMED,
)
from MiqaResearch.data.models import EtlLocationGrant, EtlSourceLocation, PipelineBinding
from MiqaResearch.readers.etl_reader import get_project_location_grants, location_grant_allows

from .audit import record_etl_event
from .exceptions import EtlLocationConflict, EtlLocationInUse, EtlLocationOutsideGrant


async def create_source_location(*, project, user, request, name, bucket, prefix) -> EtlSourceLocation:
    if not location_grant_allows(await get_project_location_grants(project), bucket, prefix):
        raise EtlLocationOutsideGrant("That bucket/prefix is not inside any of this project's location grants.")
    await _require_free_name(project, name)
    if await EtlSourceLocation.objects.filter(project=project, bucket=bucket, prefix=prefix).aexists():
        raise EtlLocationConflict("A Source Location for that bucket/prefix already exists.")

    location = await EtlSourceLocation.objects.acreate(project=project, name=name, bucket=bucket, prefix=prefix)
    await _record(EVENT_TYPE_ETL_SOURCE_LOCATION_CREATED, location, user=user, request=request, project=project)
    return location


async def rename_source_location(*, project, user, request, location_id, name) -> EtlSourceLocation:
    location = await EtlSourceLocation.objects.aget(project=project, id=location_id)
    await _require_free_name(project, name, excluding=location)
    location.name = name
    await location.asave(update_fields=["name"])
    await _record(EVENT_TYPE_ETL_SOURCE_LOCATION_RENAMED, location, user=user, request=request, project=project)
    return location


async def delete_source_location(*, project, user, request, location_id) -> None:
    location = await EtlSourceLocation.objects.aget(project=project, id=location_id)
    if await location.bindings.aexists():
        raise EtlLocationInUse("A Binding reads from this Source Location, so it can't be deleted.")
    await _record(EVENT_TYPE_ETL_SOURCE_LOCATION_DELETED, location, user=user, request=request, project=project)
    await location.adelete()


async def create_location_grant(*, project, user, request, bucket, prefix) -> EtlLocationGrant:
    if await EtlLocationGrant.objects.filter(project=project, bucket=bucket, prefix=prefix).aexists():
        raise EtlLocationConflict("That location grant already exists.")
    grant = await EtlLocationGrant.objects.acreate(project=project, bucket=bucket, prefix=prefix)
    await record_etl_event(
        EVENT_TYPE_ETL_LOCATION_GRANT_CREATED, user=user, request=request, project=project,
        metadata={"etl_location_grant_id": str(grant.id)})
    return grant


async def delete_location_grant(*, project, user, request, grant_id) -> None:
    grant = await EtlLocationGrant.objects.aget(project=project, id=grant_id)
    grants = await get_project_location_grants(project)
    remaining = [other for other in grants if other.id != grant.id]
    if await _loses_access(project, grants, remaining):
        raise EtlLocationInUse(
            "A Source Location or Binding of this project is only allowed by this grant, so it can't be deleted.")
    await record_etl_event(
        EVENT_TYPE_ETL_LOCATION_GRANT_DELETED, user=user, request=request, project=project,
        metadata={"etl_location_grant_id": str(grant.id)})
    await grant.adelete()


async def _require_free_name(project, name, *, excluding=None) -> None:
    taken = EtlSourceLocation.objects.filter(project=project, name=name)
    if excluding is not None:
        taken = taken.exclude(id=excluding.id)
    if await taken.aexists():
        raise EtlLocationConflict("A Source Location with that name already exists.")


async def _loses_access(project, grants, remaining_grants) -> bool:
    """Whether a Source Location, or a Binding's source or raw location, that `grants` allow would
    no longer be allowed by `remaining_grants`. Something no grant allowed to begin with (an older
    Binding's source, a "delete" Binding's empty raw bucket) never blocks a delete."""
    def loses(bucket, prefix):
        return location_grant_allows(grants, bucket, prefix) and not location_grant_allows(
            remaining_grants, bucket, prefix)

    async for location in EtlSourceLocation.objects.filter(project=project):
        if loses(location.bucket, location.prefix):
            return True
    async for binding in PipelineBinding.objects.filter(project=project):
        if loses(binding.source_bucket, binding.source_prefix) or loses(binding.raw_bucket, binding.raw_prefix):
            return True
    return False


async def _record(event_type, location, *, user, request, project) -> None:
    await record_etl_event(
        event_type, user=user, request=request, project=project,
        metadata={"etl_source_location_id": str(location.id)})

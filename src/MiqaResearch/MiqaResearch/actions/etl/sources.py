"""Source Locations and location grants (#268). Grants are the per-project isolation boundary for
the one platform-wide ETL credential; a Source Location is a named bucket/prefix inside a grant
that the Binding wizard offers. Callers check who may act (`EtlPermissions`); these enforce the
data rules: locations stay inside grants, bucket/prefix never change, nothing in use is deleted.

Creating a location and deleting a grant both lock the project's grant rows while they check and
write, so a concurrent grant delete can't leave a new location outside every grant.
"""
from asgiref.sync import sync_to_async
from django.db import transaction

from contract.constants.audit_log import (
    EVENT_TYPE_ETL_LOCATION_GRANT_CREATED,
    EVENT_TYPE_ETL_LOCATION_GRANT_DELETED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_CREATED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_DELETED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_RENAMED,
)
from MiqaResearch.data.models import EtlLocationGrant, EtlSourceLocation, PipelineBinding
from MiqaResearch.readers.etl_reader import location_grant_allows

from .audit import record_etl_event
from .exceptions import EtlLocationConflict, EtlLocationInUse, EtlLocationOutsideGrant


async def create_source_location(*, project, user, request, name, bucket, prefix) -> EtlSourceLocation:
    location = await sync_to_async(_create_source_location_locked)(project, name, bucket, prefix)
    await _record(EVENT_TYPE_ETL_SOURCE_LOCATION_CREATED, location, user=user, request=request, project=project)
    return location


async def rename_source_location(*, project, user, request, location, name) -> EtlSourceLocation:
    await sync_to_async(_require_free_name)(project, name, excluding=location)
    location.name = name
    await location.asave(update_fields=["name"])
    await _record(EVENT_TYPE_ETL_SOURCE_LOCATION_RENAMED, location, user=user, request=request, project=project)
    return location


async def delete_source_location(*, project, user, request, location) -> None:
    if await location.bindings.aexists():
        raise EtlLocationInUse("A Binding reads from this Source Location, so it can't be deleted.")
    await _record(EVENT_TYPE_ETL_SOURCE_LOCATION_DELETED, location, user=user, request=request, project=project)
    await location.adelete()


async def create_location_grant(*, project, user, request, bucket, prefix) -> EtlLocationGrant:
    if await EtlLocationGrant.objects.filter(project=project, bucket=bucket, prefix=prefix).aexists():
        raise EtlLocationConflict("That location grant already exists.")
    grant = await EtlLocationGrant.objects.acreate(project=project, bucket=bucket, prefix=prefix)
    await _record(EVENT_TYPE_ETL_LOCATION_GRANT_CREATED, grant, user=user, request=request, project=project)
    return grant


async def delete_location_grant(*, project, user, request, grant) -> None:
    grant_id = grant.id
    await sync_to_async(_delete_location_grant_locked)(project, grant)
    grant.id = grant_id  # Model.delete() clears the pk; the audit entry still names it
    await _record(EVENT_TYPE_ETL_LOCATION_GRANT_DELETED, grant, user=user, request=request, project=project)


def _locked_grants(project) -> list[EtlLocationGrant]:
    return list(EtlLocationGrant.objects.select_for_update().filter(project=project))


def _create_source_location_locked(project, name, bucket, prefix) -> EtlSourceLocation:
    with transaction.atomic():
        if not location_grant_allows(_locked_grants(project), bucket, prefix):
            raise EtlLocationOutsideGrant("That bucket/prefix is not inside any of this project's location grants.")
        _require_free_name(project, name)
        if EtlSourceLocation.objects.filter(project=project, bucket=bucket, prefix=prefix).exists():
            raise EtlLocationConflict("A Source Location for that bucket/prefix already exists.")
        return EtlSourceLocation.objects.create(project=project, name=name, bucket=bucket, prefix=prefix)


def _delete_location_grant_locked(project, grant) -> None:
    with transaction.atomic():
        grants = _locked_grants(project)
        remaining = [other for other in grants if other.id != grant.id]
        if _loses_access(project, grants, remaining):
            raise EtlLocationInUse(
                "A Source Location or Binding of this project is only allowed by this grant, so it can't be deleted.")
        grant.delete()


def _require_free_name(project, name, *, excluding=None) -> None:
    taken = EtlSourceLocation.objects.filter(project=project, name=name)
    if excluding is not None:
        taken = taken.exclude(id=excluding.id)
    if taken.exists():
        raise EtlLocationConflict("A Source Location with that name already exists.")


def _loses_access(project, grants, remaining_grants) -> bool:
    """Whether a Source Location, or a Binding's source or raw location, that `grants` allow would
    no longer be allowed by `remaining_grants`. Something no grant allowed to begin with (an older
    Binding's source, a "delete" Binding's empty raw bucket) never blocks a delete."""
    def loses(bucket, prefix):
        return location_grant_allows(grants, bucket, prefix) and not location_grant_allows(
            remaining_grants, bucket, prefix)

    if any(loses(location.bucket, location.prefix) for location in EtlSourceLocation.objects.filter(project=project)):
        return True
    return any(
        loses(binding.source_bucket, binding.source_prefix) or loses(binding.raw_bucket, binding.raw_prefix)
        for binding in PipelineBinding.objects.filter(project=project))


async def _record(event_type, target, *, user, request, project) -> None:
    """One audit entry per change, keyed by the target's id only (never its name or path)."""
    key = "etl_location_grant_id" if isinstance(target, EtlLocationGrant) else "etl_source_location_id"
    await record_etl_event(event_type, user=user, request=request, project=project, metadata={key: str(target.id)})

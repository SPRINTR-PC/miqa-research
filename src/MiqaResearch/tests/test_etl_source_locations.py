"""Source Location and location-grant actions (#268). A Source Location is a named bucket/prefix
inside one of the project's `EtlLocationGrant`s; grants stay the per-project isolation boundary.
Bucket/prefix are fixed once created, a location in use by a Binding can't be deleted, and a grant
can't be deleted while a location or Binding depends on it. Who may call these is the view's
concern (test_etl_permissions.py, test_dashboard_etl_sources.py).
"""
import pytest
from asgiref.sync import async_to_sync
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.audit_log import (
    EVENT_TYPE_ETL_LOCATION_GRANT_CREATED,
    EVENT_TYPE_ETL_LOCATION_GRANT_DELETED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_CREATED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_DELETED,
    EVENT_TYPE_ETL_SOURCE_LOCATION_RENAMED,
)
from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.actions.etl.exceptions import EtlLocationConflict, EtlLocationInUse, EtlLocationOutsideGrant
from MiqaResearch.actions.etl.sources import (
    create_location_grant,
    create_source_location,
    delete_location_grant,
    delete_source_location,
    rename_source_location,
)
from MiqaResearch.data.models import (
    AuditLog,
    EtlLocationGrant,
    EtlScript,
    EtlScriptVersion,
    EtlSourceLocation,
    PipelineBinding,
    ResearchProject,
)


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Sources project", description="")


@pytest.fixture
def grant(project):
    return EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="redcap/")


def _call(action, **kwargs):
    return async_to_sync(action)(user=None, request=None, **kwargs)


def _binding(project, *, source_prefix="redcap/a/", raw_bucket="raw", raw_retention="move", source_location=None):
    script = EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("s.py", b"print()"), sha256="0" * 64)
    return PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix=source_prefix, script_version=version,
        raw_bucket=raw_bucket, raw_prefix="", raw_retention=raw_retention, source_location=source_location)


def _events(event_type):
    return list(AuditLog.objects.filter(event_type=event_type))


# Source Locations

def test_a_location_inside_a_grant_is_created_and_audited_by_id_only(project, grant):
    location = _call(create_source_location, project=project, name="REDCap A", bucket="incoming", prefix="redcap/a/")

    assert (location.project, location.name, location.bucket, location.prefix) == (
        project, "REDCap A", "incoming", "redcap/a/")
    [event] = _events(EVENT_TYPE_ETL_SOURCE_LOCATION_CREATED)
    assert event.metadata == {"etl_source_location_id": str(location.id)}


@pytest.mark.parametrize("bucket, prefix", [("incoming", "other/"), ("elsewhere", "redcap/")])
def test_a_location_outside_every_grant_is_rejected(project, grant, bucket, prefix):
    with pytest.raises(EtlLocationOutsideGrant):
        _call(create_source_location, project=project, name="Outside", bucket=bucket, prefix=prefix)

    assert not EtlSourceLocation.objects.exists()


def test_another_projects_grant_does_not_count(project):
    other = ResearchProject.objects.create(name="Other", description="")
    EtlLocationGrant.objects.create(project=other, bucket="incoming", prefix="")

    with pytest.raises(EtlLocationOutsideGrant):
        _call(create_source_location, project=project, name="Theirs", bucket="incoming", prefix="")


@pytest.mark.parametrize("name, prefix", [("REDCap A", "redcap/b/"), ("Different", "redcap/a/")])
def test_name_and_bucket_prefix_are_each_unique_per_project(project, grant, name, prefix):
    _call(create_source_location, project=project, name="REDCap A", bucket="incoming", prefix="redcap/a/")

    with pytest.raises(EtlLocationConflict):
        _call(create_source_location, project=project, name=name, bucket="incoming", prefix=prefix)


def test_rename_changes_only_the_name(project, grant):
    location = EtlSourceLocation.objects.create(project=project, name="Old", bucket="incoming", prefix="redcap/a/")

    _call(rename_source_location, project=project, location_id=location.id, name="New")

    location.refresh_from_db()
    assert (location.name, location.bucket, location.prefix) == ("New", "incoming", "redcap/a/")
    assert len(_events(EVENT_TYPE_ETL_SOURCE_LOCATION_RENAMED)) == 1


def test_rename_to_a_taken_name_is_a_conflict(project, grant):
    EtlSourceLocation.objects.create(project=project, name="Taken", bucket="incoming", prefix="redcap/a/")
    location = EtlSourceLocation.objects.create(project=project, name="Mine", bucket="incoming", prefix="redcap/b/")

    with pytest.raises(EtlLocationConflict):
        _call(rename_source_location, project=project, location_id=location.id, name="Taken")


def test_an_unused_location_is_deleted(project, grant):
    location = EtlSourceLocation.objects.create(project=project, name="Unused", bucket="incoming", prefix="redcap/a/")

    _call(delete_source_location, project=project, location_id=location.id)

    assert not EtlSourceLocation.objects.exists()
    assert len(_events(EVENT_TYPE_ETL_SOURCE_LOCATION_DELETED)) == 1


def test_a_location_a_binding_uses_cannot_be_deleted(project, grant):
    location = EtlSourceLocation.objects.create(project=project, name="Used", bucket="incoming", prefix="redcap/a/")
    _binding(project, source_location=location)

    with pytest.raises(EtlLocationInUse):
        _call(delete_source_location, project=project, location_id=location.id)

    assert EtlSourceLocation.objects.filter(id=location.id).exists()


def test_another_projects_location_is_not_found(project, grant):
    other = ResearchProject.objects.create(name="Other", description="")
    theirs = EtlSourceLocation.objects.create(project=other, name="Theirs", bucket="x", prefix="")

    with pytest.raises(EtlSourceLocation.DoesNotExist):
        _call(delete_source_location, project=project, location_id=theirs.id)


# Location grants

def test_a_grant_is_created_and_audited(project):
    created = _call(create_location_grant, project=project, bucket="incoming", prefix="")

    assert (created.project, created.bucket, created.prefix) == (project, "incoming", "")
    [event] = _events(EVENT_TYPE_ETL_LOCATION_GRANT_CREATED)
    assert event.metadata == {"etl_location_grant_id": str(created.id)}


def test_a_duplicate_grant_is_a_conflict(project, grant):
    with pytest.raises(EtlLocationConflict):
        _call(create_location_grant, project=project, bucket="incoming", prefix="redcap/")


def test_an_unused_grant_is_deleted(project, grant):
    _call(delete_location_grant, project=project, grant_id=grant.id)

    assert not EtlLocationGrant.objects.exists()
    assert len(_events(EVENT_TYPE_ETL_LOCATION_GRANT_DELETED)) == 1


def test_a_grant_a_source_location_depends_on_cannot_be_deleted(project, grant):
    EtlSourceLocation.objects.create(project=project, name="Inside", bucket="incoming", prefix="redcap/a/")

    with pytest.raises(EtlLocationInUse):
        _call(delete_location_grant, project=project, grant_id=grant.id)


@pytest.mark.parametrize("binding_kwargs", [{}, {"source_prefix": "elsewhere/", "raw_bucket": "incoming"}])
def test_a_grant_a_bindings_source_or_raw_location_depends_on_cannot_be_deleted(project, grant, binding_kwargs):
    EtlLocationGrant.objects.create(project=project, bucket="raw", prefix="")
    _binding(project, **binding_kwargs)
    if binding_kwargs:  # the source is covered by a second grant; only the raw bucket needs this one
        EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="elsewhere/")
        PipelineBinding.objects.update(raw_prefix="redcap/")

    with pytest.raises(EtlLocationInUse):
        _call(delete_location_grant, project=project, grant_id=grant.id)


def test_a_grant_still_covered_by_another_grant_can_be_deleted(project, grant):
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    EtlSourceLocation.objects.create(project=project, name="Inside", bucket="incoming", prefix="redcap/a/")

    _call(delete_location_grant, project=project, grant_id=grant.id)

    assert not EtlLocationGrant.objects.filter(id=grant.id).exists()


def test_a_delete_retention_binding_with_no_raw_bucket_does_not_block_unrelated_grant_deletes(project, grant):
    unrelated = EtlLocationGrant.objects.create(project=project, bucket="lab", prefix="")
    _binding(project, raw_bucket="", raw_retention="delete")

    _call(delete_location_grant, project=project, grant_id=unrelated.id)

    assert not EtlLocationGrant.objects.filter(id=unrelated.id).exists()

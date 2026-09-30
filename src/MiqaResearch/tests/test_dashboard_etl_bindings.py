"""View tests for the ETL Bindings section's manage action (#158): creating a `PipelineBinding`
through the wizard, constrained to buckets the project's `EtlLocationGrant`s allow. Role-boundary
logic itself is unit-tested in test_etl_permissions.py; this file checks the wizard view actually
enforces it, the location-grant constraint, and that a create writes an audit entry.
"""
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_ETL_BINDING_CREATED, EVENT_TYPE_ETL_BINDING_UPDATED
from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM, ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import (
    AuditLog,
    EtlLocationGrant,
    EtlPendingGroup,
    EtlProcessedFile,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)

User = get_user_model()

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="ETL Bindings Project", description="desc")


@pytest.fixture
def native_version(db):
    script = EtlScript.objects.create(name="Native importer", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    return EtlScriptVersion.objects.create(
        script=script, version=1,
        source=SimpleUploadedFile("script.py", b"print()", content_type="text/x-python"), sha256="0" * 64)


def _user_with_role(project, role_name):
    user = User.objects.create_user(username=f"user-{role_name.lower().replace(' ', '-')}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def _client_as(user):
    client = Client()
    client.force_login(user)
    return client


def _bindings_url(project):
    return reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=bindings"


def _create_url(project):
    return reverse("dashboard_tab_etl_bindings_create", args=[project.id])


def _payload(native_version, **overrides):
    payload = {
        "source_bucket": "incoming", "source_prefix": "redcap/",
        "script_version": str(native_version.id),
        "raw_bucket": "raw", "raw_prefix": "",
        "grouping_mode": "file", "quiescence_seconds": "", "config": "",
        "timeout_seconds_override": "", "memory_mb_override": "", "cpu_millicores_override": "",
    }
    payload.update(overrides)
    return payload


def _grant_incoming_and_raw(project):
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=project, bucket="raw", prefix="")


def _edit_url(project, binding):
    return reverse("dashboard_tab_etl_binding_edit", args=[project.id, binding.id])


def _new_version(script, version):
    return EtlScriptVersion.objects.create(
        script=script, version=version,
        source=SimpleUploadedFile("script.py", f"# v{version}".encode(), content_type="text/x-python"),
        sha256=str(version) * 64)


def _existing_binding(project, script_version, **fields):
    return PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix="redcap/", script_version=script_version,
        raw_bucket="raw", raw_prefix="", **fields)


def _edit_payload(binding, **overrides):
    payload = {
        "script_version": str(binding.script_version_id),
        "raw_bucket": binding.raw_bucket, "raw_prefix": binding.raw_prefix,
        "grouping_mode": binding.grouping_mode, "quiescence_seconds": str(binding.quiescence_seconds),
        "config": json.dumps(binding.config),
        "timeout_seconds_override": "", "memory_mb_override": "", "cpu_millicores_override": "",
    }
    payload.update(overrides)
    return payload


# --- Visibility -----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_role_outside_the_visible_set_gets_404(project):
    client = _client_as(_user_with_role(project, "Annotator"))

    assert client.get(_bindings_url(project)).status_code == 404


@pytest.mark.django_db
def test_a_read_only_role_sees_bindings_but_no_wizard(project):
    client = _client_as(_user_with_role(project, "PI"))

    body = client.get(_bindings_url(project)).content.decode()

    assert "No pipelines connected yet" in body
    assert "New binding" not in body


@pytest.mark.django_db
def test_each_binding_shows_the_datatype_its_script_produces(project):
    script = EtlScript.objects.create(
        name="Visit import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="visit_occurrence")
    version = EtlScriptVersion.objects.create(
        script=script, version=1,
        source=SimpleUploadedFile("script.py", b"print()", content_type="text/x-python"), sha256="0" * 64)
    PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix="visits/", script_version=version, raw_bucket="raw")
    client = _client_as(_user_with_role(project, "Investigator"))  # read-only: no wizard listing script choices

    body = client.get(_bindings_url(project)).content.decode()

    assert "visit_occurrence" in body


@pytest.mark.django_db
def test_a_read_only_role_cannot_post_a_create_action(project, native_version):
    client = _client_as(_user_with_role(project, "PI"))
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")

    response = client.post(_create_url(project), _payload(native_version), **HTMX)

    assert response.status_code == 403
    assert not PipelineBinding.objects.exists()


# --- Location grant constraint ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_binding_outside_every_location_grant_is_rejected(project, native_version):
    client = _client_as(_user_with_role(project, "Data Manager"))
    # no EtlLocationGrant at all for this project

    response = client.post(_create_url(project), _payload(native_version), **HTMX)

    assert response.status_code == 200
    assert not PipelineBinding.objects.exists()
    assert "not been granted access" in response.content.decode()


@pytest.mark.django_db
def test_a_prefix_outside_a_narrower_grant_is_rejected(project, native_version):
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="allowed/")
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(
        _create_url(project), _payload(native_version, source_prefix="elsewhere/"), **HTMX)

    assert response.status_code == 200
    assert not PipelineBinding.objects.exists()


@pytest.mark.django_db
def test_a_raw_bucket_outside_every_location_grant_is_rejected(project, native_version):
    # only the source bucket is granted -- the raw destination needs its own grant too
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_create_url(project), _payload(native_version, raw_bucket="ungranted-raw"), **HTMX)

    assert response.status_code == 200
    assert not PipelineBinding.objects.exists()
    assert "raw bucket/prefix" in response.content.decode()


@pytest.mark.django_db
def test_a_data_manager_can_create_a_binding_within_a_granted_bucket(project, native_version):
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=project, bucket="raw", prefix="")
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_create_url(project), _payload(native_version), **HTMX)

    assert response.status_code == 200
    binding = PipelineBinding.objects.get(project=project)
    assert binding.source_bucket == "incoming"
    assert binding.script_version_id == native_version.id
    assert "incoming/redcap/" in response.content.decode()


@pytest.mark.django_db
def test_a_data_manager_can_create_a_folder_grouped_binding_with_its_own_quiescence_window(project, native_version):
    _grant_incoming_and_raw(project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project), _payload(native_version, grouping_mode="folder", quiescence_seconds="900"), **HTMX)

    binding = PipelineBinding.objects.get(project=project)
    assert binding.grouping_mode == "folder"
    assert binding.quiescence_seconds == 900


@pytest.mark.django_db
def test_a_bindings_config_is_set_in_the_wizard(project, native_version):
    _grant_incoming_and_raw(project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_create_url(project), _payload(native_version, config='{"delimiter": ";", "skip_rows": 2}'), **HTMX)

    assert PipelineBinding.objects.get(project=project).config == {"delimiter": ";", "skip_rows": 2}


@pytest.mark.django_db
@pytest.mark.parametrize("config", ['{"delimiter": ', '[";"]', '"a string"'])
def test_a_config_that_is_not_a_json_object_is_rejected(project, native_version, config):
    _grant_incoming_and_raw(project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_create_url(project), _payload(native_version, config=config), **HTMX)

    assert not PipelineBinding.objects.exists()
    assert "etl-form-error" in response.content.decode()


@pytest.mark.django_db
def test_creating_a_binding_records_an_audit_event_with_no_data_values(project, native_version):
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=project, bucket="raw", prefix="")
    user = _user_with_role(project, "Admin")
    client = _client_as(user)

    client.post(_create_url(project), _payload(native_version), **HTMX)

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_BINDING_CREATED)
    assert entry.user_id == user.id
    assert entry.project_id == project.id
    assert "incoming" not in str(entry.metadata)
    assert set(entry.metadata.keys()) == {"etl_pipeline_binding_id"}


@pytest.mark.django_db
def test_a_duplicate_source_bucket_and_prefix_is_rejected(project, native_version):
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=project, bucket="raw", prefix="")
    PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix="redcap/", script_version=native_version,
        raw_bucket="raw", raw_prefix="")
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_create_url(project), _payload(native_version), **HTMX)

    assert response.status_code == 200
    assert PipelineBinding.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_a_scripts_own_project_custom_version_is_selectable_but_another_projects_is_not(project, db):
    other_project = ResearchProject.objects.create(name="Other project", description="desc")
    own_script = EtlScript.objects.create(name="Own", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    own_version = EtlScriptVersion.objects.create(
        script=own_script, version=1,
        source=SimpleUploadedFile("s.py", b"x", content_type="text/x-python"), sha256="1" * 64)
    other_script = EtlScript.objects.create(name="Other", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=other_project)
    other_version = EtlScriptVersion.objects.create(
        script=other_script, version=1,
        source=SimpleUploadedFile("s.py", b"y", content_type="text/x-python"), sha256="2" * 64)
    EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=project, bucket="raw", prefix="")
    client = _client_as(_user_with_role(project, "Admin"))

    own_response = client.post(_create_url(project), _payload(own_version, source_prefix="own/"), **HTMX)
    other_response = client.post(_create_url(project), _payload(other_version, source_prefix="other/"), **HTMX)

    assert PipelineBinding.objects.filter(project=project, source_prefix="own/").exists()
    assert not PipelineBinding.objects.filter(project=project, source_prefix="other/").exists()
    assert own_response.status_code == 200
    assert other_response.status_code == 200


# --- Edit binding (#224) --------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_can_re_pin_a_binding_to_a_newer_script_version(project, native_version):
    _grant_incoming_and_raw(project)
    binding = _existing_binding(project, native_version)
    newer = _new_version(native_version.script, 2)
    user = _user_with_role(project, "Data Manager")

    _client_as(user).post(_edit_url(project, binding), _edit_payload(binding, script_version=str(newer.id)), **HTMX)

    binding.refresh_from_db()
    assert binding.script_version_id == newer.id
    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_BINDING_UPDATED)
    assert entry.user_id == user.id
    assert entry.project_id == project.id
    assert entry.metadata == {"etl_pipeline_binding_id": str(binding.id)}


@pytest.mark.django_db
def test_a_binding_edit_updates_grouping_config_overrides_and_raw_destination(project, native_version):
    _grant_incoming_and_raw(project)
    EtlLocationGrant.objects.create(project=project, bucket="archive", prefix="")
    binding = _existing_binding(project, native_version)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_edit_url(project, binding), _edit_payload(
        binding, grouping_mode="folder", quiescence_seconds="120", config='{"delimiter": ";"}',
        timeout_seconds_override="60", raw_bucket="archive", raw_prefix="lab/"), **HTMX)

    binding.refresh_from_db()
    assert (binding.grouping_mode, binding.quiescence_seconds) == ("folder", 120)
    assert binding.config == {"delimiter": ";"}
    assert binding.timeout_seconds_override == 60
    assert (binding.raw_bucket, binding.raw_prefix) == ("archive", "lab/")


@pytest.mark.django_db
def test_a_binding_edit_never_changes_its_source_location(project, native_version):
    _grant_incoming_and_raw(project)
    binding = _existing_binding(project, native_version)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _edit_url(project, binding), _edit_payload(binding, source_bucket="incoming", source_prefix="other/"), **HTMX)

    binding.refresh_from_db()
    assert (binding.source_bucket, binding.source_prefix) == ("incoming", "redcap/")


@pytest.mark.django_db
def test_a_binding_edit_to_an_ungranted_raw_destination_is_rejected(project, native_version):
    _grant_incoming_and_raw(project)
    binding = _existing_binding(project, native_version)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_edit_url(project, binding), _edit_payload(binding, raw_bucket="ungranted"), **HTMX)

    binding.refresh_from_db()
    assert binding.raw_bucket == "raw"
    assert "raw bucket/prefix" in response.content.decode()
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_BINDING_UPDATED).exists()


@pytest.mark.django_db
def test_a_binding_cannot_be_re_pinned_to_an_archived_scripts_version(project, native_version):
    _grant_incoming_and_raw(project)
    binding = _existing_binding(project, native_version)
    archived = EtlScript.objects.create(
        name="Old", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, archived_at=timezone.now())
    archived_version = _new_version(archived, 1)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_edit_url(project, binding), _edit_payload(binding, script_version=str(archived_version.id)), **HTMX)

    binding.refresh_from_db()
    assert binding.script_version_id == native_version.id


@pytest.mark.django_db
def test_a_read_only_role_cannot_edit_a_binding(project, native_version):
    binding = _existing_binding(project, native_version)
    client = _client_as(_user_with_role(project, "Investigator"))

    response = client.post(_edit_url(project, binding), _edit_payload(binding, grouping_mode="folder"), **HTMX)

    binding.refresh_from_db()
    assert response.status_code == 403
    assert binding.grouping_mode == "file"


@pytest.mark.django_db
def test_another_projects_binding_cannot_be_edited(project, native_version):
    other_project = ResearchProject.objects.create(name="Other project", description="desc")
    binding = _existing_binding(other_project, native_version)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_edit_url(project, binding), _edit_payload(binding, grouping_mode="folder"), **HTMX)

    assert response.status_code == 404


@pytest.mark.django_db
def test_switching_to_folder_grouping_starts_quiescence_for_files_already_seen_but_not_queued(project, native_version):
    _grant_incoming_and_raw(project)
    binding = _existing_binding(project, native_version)
    EtlProcessedFile.objects.create(binding=binding, bucket="incoming", key="redcap/visit-1/a.csv")
    EtlProcessedFile.objects.create(binding=binding, bucket="incoming", key="redcap/top-level.csv")
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_edit_url(project, binding), _edit_payload(binding, grouping_mode="folder"), **HTMX)

    assert set(EtlPendingGroup.objects.filter(binding=binding).values_list("group_key", flat=True)) == {"visit-1", ""}


@pytest.mark.django_db
def test_switching_to_per_file_grouping_drops_pending_folder_groups(project, native_version):
    _grant_incoming_and_raw(project)
    binding = _existing_binding(project, native_version, grouping_mode="folder")
    EtlPendingGroup.objects.create(binding=binding, group_key="visit-1", last_seen_at=timezone.now())
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_edit_url(project, binding), _edit_payload(binding, grouping_mode="file"), **HTMX)

    assert not EtlPendingGroup.objects.filter(binding=binding).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(("role_name", "can_edit"), [("Data Manager", True), ("Investigator", False)])
def test_only_managers_get_an_edit_form_for_each_binding(project, native_version, role_name, can_edit):
    binding = _existing_binding(project, native_version)
    client = _client_as(_user_with_role(project, role_name))

    body = client.get(_bindings_url(project)).content.decode()

    assert (_edit_url(project, binding) in body) is can_edit


@pytest.mark.django_db
def test_each_binding_shows_how_it_groups_files(project, native_version):
    _existing_binding(project, native_version, grouping_mode="folder", quiescence_seconds=600)
    client = _client_as(_user_with_role(project, "Investigator"))

    body = client.get(_bindings_url(project)).content.decode()

    assert "Folder, with quiescence wait (600 s)" in body

"""View tests for the ETL Scripts section's manage actions (#158): create/edit/archive a custom
Script and add a Version, gated by the ETL permissions policy, each writing an `etl_*` AuditLog
entry. Role-boundary logic itself is unit-tested in test_etl_permissions.py; this file checks that
the dashboard views actually enforce it and that the real DB/audit side effects happen.
"""
import re

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from contract.constants.audit_log import (
    EVENT_TYPE_ETL_SCRIPT_ARCHIVED,
    EVENT_TYPE_ETL_SCRIPT_CREATED,
    EVENT_TYPE_ETL_SCRIPT_UPDATED,
    EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED,
)
from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM, ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import (
    AuditLog,
    EtlScript,
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
    return ResearchProject.objects.create(name="ETL Scripts Project", description="desc")


def _user_with_role(project, role_name):
    user = User.objects.create_user(username=f"user-{role_name.lower().replace(' ', '-')}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def _client_as(user):
    client = Client()
    client.force_login(user)
    return client


def _scripts_url(project):
    return reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=scripts"


def _create_url(project):
    return reverse("dashboard_tab_etl_scripts_create", args=[project.id])


def _edit_url(project, script):
    return reverse("dashboard_tab_etl_script_edit", args=[project.id, script.id])


def _version_url(project, script):
    return reverse("dashboard_tab_etl_script_version_create", args=[project.id, script.id])


def _archive_url(project, script):
    return reverse("dashboard_tab_etl_script_archive", args=[project.id, script.id])


def _upload(name=b"print('hi')", filename="script.py"):
    return SimpleUploadedFile(filename, name, content_type="text/x-python")


# --- Visibility -----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_role_outside_the_visible_set_gets_404_on_the_scripts_section(project):
    client = _client_as(_user_with_role(project, "Contributor"))

    response = client.get(_scripts_url(project))

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_read_only_role_sees_the_section_but_no_create_form(project):
    client = _client_as(_user_with_role(project, "Investigator"))

    body = client.get(_scripts_url(project)).content.decode()

    assert "No scripts registered yet" in body
    assert 'name="name"' not in body  # no create-script form rendered


@pytest.mark.django_db
def test_a_read_only_role_cannot_post_a_create_action(project):
    client = _client_as(_user_with_role(project, "Investigator"))

    response = client.post(_create_url(project), {"name": "x", "description": ""}, **HTMX)

    assert response.status_code == 403
    assert not EtlScript.objects.exists()


# --- Create custom script ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_can_create_a_custom_script(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project),
        {"name": "REDCap import", "description": "Imports REDCap exports", "source": _upload()},
        **HTMX,
    )

    assert response.status_code == 200
    script = EtlScript.objects.get(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
    assert script.name == "REDCap import"
    assert script.versions.count() == 1
    assert "REDCap import" in response.content.decode()


@pytest.mark.django_db
def test_creating_a_script_records_an_audit_event_scoped_to_the_project_with_no_data_values(project):
    user = _user_with_role(project, "Admin")
    client = _client_as(user)

    client.post(_create_url(project), {"name": "REDCap import", "description": "", "source": _upload()}, **HTMX)

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_SCRIPT_CREATED)
    assert entry.user_id == user.id
    assert entry.project_id == project.id
    assert "REDCap" not in str(entry.metadata)
    assert set(entry.metadata.keys()) == {"etl_script_id"}


@pytest.mark.django_db
def test_an_oversized_source_file_is_rejected_with_a_form_error(project, settings):
    settings.ETL_SCRIPT_MAX_SOURCE_BYTES = 4
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(
        _create_url(project), {"name": "Too big", "description": "", "source": _upload(b"way too many bytes")}, **HTMX)

    assert response.status_code == 200
    assert not EtlScript.objects.filter(name="Too big").exists()
    assert "at most 4 bytes" in response.content.decode()


# --- Edit and add version ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_can_edit_a_custom_scripts_name_and_description(project):
    script = EtlScript.objects.create(name="Old name", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_edit_url(project, script), {"name": "New name", "description": "Updated"}, **HTMX)

    script.refresh_from_db()
    assert response.status_code == 200
    assert script.name == "New name"
    assert script.description == "Updated"
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_UPDATED, project=project).exists()


@pytest.mark.django_db
def test_a_data_manager_can_add_a_new_version_to_a_custom_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_version_url(project, script), {"source": _upload(b"v2 source")}, **HTMX)

    assert response.status_code == 200
    assert list(script.versions.order_by("version").values_list("version", flat=True)) == [1, 2]
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED, project=project).exists()


@pytest.mark.django_db
def test_a_native_script_cannot_be_edited_even_by_an_admin(project):
    native = EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_edit_url(project, native), {"name": "Hijacked", "description": ""}, **HTMX)

    native.refresh_from_db()
    assert response.status_code == 200
    assert native.name == "Native"
    assert "only this project" in response.content.decode().lower()


# --- Archive (Admin-only) ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_cannot_archive_a_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_archive_url(project, script), {}, **HTMX)

    script.refresh_from_db()
    assert response.status_code == 403
    assert script.archived_at is None


@pytest.mark.django_db
def test_an_admin_can_archive_a_custom_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_archive_url(project, script), {}, **HTMX)

    script.refresh_from_db()
    assert response.status_code == 200
    assert script.archived_at is not None
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_ARCHIVED, project=project).exists()


@pytest.mark.django_db
def test_archiving_a_native_script_is_rejected_with_a_visible_error(project):
    native = EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_archive_url(project, native), {}, **HTMX)

    native.refresh_from_db()
    assert response.status_code == 200
    assert native.archived_at is None
    assert "only this project" in response.content.decode().lower()


@pytest.mark.django_db
def test_an_archived_scripts_manage_controls_no_longer_render(project):
    script = EtlScript.objects.create(name="Gone", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    admin = _user_with_role(project, "Admin")
    client = _client_as(admin)
    client.post(_archive_url(project, script), {}, **HTMX)

    body = client.get(_scripts_url(project)).content.decode()

    assert "archived" in body
    row = re.search(r"<li>.*?Gone.*?</li>", body, re.DOTALL)
    assert row is not None
    assert "Archive" not in row.group(0)

"""View tests for the ETL Defaults section (#158): native scripts read-only, plus the Admin-only
project overrides form (`EtlProjectSettings.log_retention_days` / `max_script_source_bytes`).
Role-boundary logic itself is unit-tested in test_etl_permissions.py.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from contract.constants.audit_log import EVENT_TYPE_ETL_SETTINGS_UPDATED
from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import (
    AuditLog,
    EtlProjectSettings,
    EtlScript,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)

User = get_user_model()

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="ETL Defaults Project", description="desc")


def _user_with_role(project, role_name):
    user = User.objects.create_user(username=f"user-{role_name.lower().replace(' ', '-')}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def _client_as(user):
    client = Client()
    client.force_login(user)
    return client


def _defaults_url(project):
    return reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=defaults"


def _update_url(project):
    return reverse("dashboard_tab_etl_defaults_update", args=[project.id])


@pytest.mark.django_db
def test_a_role_outside_the_visible_set_gets_404(project):
    client = _client_as(_user_with_role(project, "Contributor"))

    assert client.get(_defaults_url(project)).status_code == 404


@pytest.mark.django_db
def test_native_scripts_are_listed_read_only_for_every_visible_role(project):
    EtlScript.objects.create(name="Native importer", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    client = _client_as(_user_with_role(project, "Investigator"))

    body = client.get(_defaults_url(project)).content.decode()

    assert "Native importer" in body


@pytest.mark.django_db
def test_a_data_manager_sees_no_overrides_form(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    body = client.get(_defaults_url(project)).content.decode()

    assert 'name="log_retention_days"' not in body


@pytest.mark.django_db
def test_a_data_manager_cannot_post_an_overrides_update(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_update_url(project), {"log_retention_days": "30", "max_script_source_bytes": ""}, **HTMX)

    assert response.status_code == 403
    assert not EtlProjectSettings.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_an_admin_sees_the_overrides_form(project):
    client = _client_as(_user_with_role(project, "Admin"))

    body = client.get(_defaults_url(project)).content.decode()

    assert 'name="log_retention_days"' in body


@pytest.mark.django_db
def test_an_admin_can_set_project_overrides(project):
    user = _user_with_role(project, "Admin")
    client = _client_as(user)

    response = client.post(
        _update_url(project), {"log_retention_days": "30", "max_script_source_bytes": "1048576"}, **HTMX)

    assert response.status_code == 200
    settings_obj = EtlProjectSettings.objects.get(project=project)
    assert settings_obj.log_retention_days == 30
    assert settings_obj.max_script_source_bytes == 1048576


@pytest.mark.django_db
def test_updating_overrides_records_an_audit_event_with_no_data_values(project):
    user = _user_with_role(project, "Admin")
    client = _client_as(user)

    client.post(_update_url(project), {"log_retention_days": "30", "max_script_source_bytes": ""}, **HTMX)

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_SETTINGS_UPDATED)
    assert entry.user_id == user.id
    assert entry.project_id == project.id
    # Only the settings row's id -- never the values saved (an exact match, since a random id can contain "30").
    assert entry.metadata == {"etl_project_settings_id": str(EtlProjectSettings.objects.get(project=project).id)}


@pytest.mark.django_db
def test_overrides_can_be_cleared_back_to_null(project):
    EtlProjectSettings.objects.create(project=project, log_retention_days=30, max_script_source_bytes=1024)
    client = _client_as(_user_with_role(project, "Admin"))

    client.post(_update_url(project), {"log_retention_days": "", "max_script_source_bytes": ""}, **HTMX)

    settings_obj = EtlProjectSettings.objects.get(project=project)
    assert settings_obj.log_retention_days is None
    assert settings_obj.max_script_source_bytes is None

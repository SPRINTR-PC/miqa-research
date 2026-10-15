"""The project dashboard's API clients tab (#277, ADR 0027): who may issue, rotate and revoke machine
clients and grant `dicom:raw`, the secret shown once, and the audit trail of every change.

Seams: the dashboard views (htmx requests from a logged-in user) and the OAuth2 token endpoint, which
shows whether an issued secret and its scopes actually work.
"""
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from oauth2_provider.models import AccessToken, Application

from contract.constants.audit_log import (
    DATA_ACCESS_EVENT_TYPES,
    EVENT_TYPE_API_CLIENT_ISSUED,
    EVENT_TYPE_API_CLIENT_REVOKED,
    EVENT_TYPE_API_CLIENT_SECRET_ROTATED,
    EVENT_TYPE_API_CLIENT_UPDATED,
    EVENT_TYPE_DICOM_RAW_GRANTED,
    EVENT_TYPE_DICOM_RAW_REVOKED,
)
from MiqaResearch.data.models import (
    AuditLog,
    ClientBinding,
    Clinic,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.data.models.research_project import ResearchProjectClinicMap

User = get_user_model()
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def project(db):
    project = ResearchProject.objects.create(name="Imaging", description="desc")
    for code in "AB":
        ResearchProjectClinicMap.objects.create(
            project=project, clinic=Clinic.objects.create(clinic_code=f"S-{code}", clinic_name=f"Site {code}"))
    return project


def _site(code):
    return Clinic.objects.get(clinic_code=f"S-{code}")


def _member(project, role_name, **user_flags):
    user = User.objects.create_user(username=f"user-{User.objects.count()}", password="pw", **user_flags)
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    client = Client()
    client.force_login(user)
    client.user = user
    return client


def _admin(project):
    return _member(project, "Admin")


def _url(name, project, *args):
    return reverse(name, args=[project.id, *args])


def _issue(client, project, *, name="Pipeline", site="", dicom_raw=False):
    data = {"name": name, "clinic": str(site.id) if site else ""}
    if dicom_raw:
        data["dicom_raw"] = "on"
    return client.post(_url("dashboard_tab_api_client_issue", project), data, **HTMX)


def _secret_in(response) -> str:
    match = re.search(r'data-client-secret="([^"]+)"', response.content.decode())
    assert match, "secret not shown"
    return match.group(1)


def _token_status(application, secret, scope="read"):
    return Client().post("/o/token/", {
        "grant_type": "client_credentials", "client_id": application.client_id, "client_secret": secret,
        "scope": scope,
    }).status_code


def _events(*event_types):
    return list(AuditLog.objects.filter(event_type__in=event_types).order_by("logtime"))


# --- Who may manage clients ------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("make_client", [_admin, lambda p: _member(p, "Contributor", is_superuser=True)])
def test_project_admins_and_superusers_see_the_api_clients_tab(project, make_client):
    response = make_client(project).get(_url("dashboard_tab_api_clients", project), **HTMX)

    assert response.status_code == 200
    assert _url("dashboard_tab_api_client_issue", project) in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["PI", "Data Manager", "Contributor", "Annotator"])
def test_other_roles_get_404_on_the_tab_and_every_action(project, role):
    binding = _bound(project)
    client = _member(project, role, is_staff=True)

    assert client.get(_url("dashboard_tab_api_clients", project), **HTMX).status_code == 404
    assert _issue(client, project).status_code == 404
    for action in ("update", "rotate", "revoke"):
        url = _url(f"dashboard_tab_api_client_{action}", project, binding.id)
        assert client.post(url, {"clinic": ""}, **HTMX).status_code == 404, action
    assert ClientBinding.objects.count() == 1


@pytest.mark.django_db
def test_an_admin_of_another_project_cannot_manage_this_projects_clients(project):
    other = ResearchProject.objects.create(name="Other", description="")
    binding = _bound(project)
    client = _admin(other)

    assert client.get(_url("dashboard_tab_api_clients", project), **HTMX).status_code == 404
    assert client.post(_url("dashboard_tab_api_client_revoke", other, binding.id), **HTMX).status_code == 404
    assert ClientBinding.objects.filter(pk=binding.pk).exists()


def _bound(project, dicom_raw=False):
    application = Application.objects.create(
        name="existing", client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS)
    return ClientBinding.objects.create(application=application, research_project=project, dicom_raw=dicom_raw)


# --- Issue ------------------------------------------------------------------------


@pytest.mark.django_db
def test_issuing_binds_a_client_to_the_project_and_shows_its_secret_once(project):
    admin = _admin(project)

    response = _issue(admin, project, name="Radiomics", site=_site("A"))

    assert response.status_code == 200
    binding = ClientBinding.objects.get()
    assert binding.research_project == project
    assert binding.clinic == _site("A")
    assert not binding.dicom_raw
    assert binding.application.user is None  # belongs to the project, not the issuer
    secret = _secret_in(response)
    assert binding.application.client_id in response.content.decode()
    assert _token_status(binding.application, secret) == 200
    assert _token_status(binding.application, secret, "read dicom:raw") == 400
    assert secret not in admin.get(_url("dashboard_tab_api_clients", project), **HTMX).content.decode()
    (issued,) = _events(EVENT_TYPE_API_CLIENT_ISSUED)
    assert issued.user == admin.user
    assert issued.project == project
    assert secret not in str(issued.metadata)


@pytest.mark.django_db
def test_issuing_with_raw_access_is_a_data_access_event(project):
    admin = _admin(project)

    secret = _secret_in(_issue(admin, project, dicom_raw=True))

    binding = ClientBinding.objects.get()
    assert binding.dicom_raw and binding.clinic is None
    assert _token_status(binding.application, secret, "read dicom:raw") == 200
    (granted,) = _events(EVENT_TYPE_DICOM_RAW_GRANTED)
    assert granted.event_type in DATA_ACCESS_EVENT_TYPES
    assert granted.metadata["client_id"] == binding.application.client_id


@pytest.mark.django_db
def test_a_site_outside_the_project_is_refused(project):
    elsewhere = Clinic.objects.create(clinic_code="S-X", clinic_name="Elsewhere")

    response = _issue(_admin(project), project, site=elsewhere)

    assert response.status_code == 200
    assert not ClientBinding.objects.exists()
    assert not Application.objects.exists()


@pytest.mark.django_db
def test_the_client_keeps_working_after_the_issuer_loses_their_role(project):
    admin = _admin(project)
    secret = _secret_in(_issue(admin, project))

    ResearchProjectUserRoleMap.objects.filter(user=admin.user).delete()

    assert _token_status(ClientBinding.objects.get().application, secret) == 200


# --- Update, rotate, revoke --------------------------------------------------------


@pytest.mark.django_db
def test_granting_and_revoking_raw_access_are_audited_as_data_access(project):
    binding = _bound(project)
    admin = _admin(project)
    url = _url("dashboard_tab_api_client_update", project, binding.id)

    admin.post(url, {"clinic": "", "dicom_raw": "on"}, **HTMX)
    binding.refresh_from_db()
    assert binding.dicom_raw
    admin.post(url, {"clinic": ""}, **HTMX)
    binding.refresh_from_db()
    assert not binding.dicom_raw

    assert [e.event_type for e in _events(EVENT_TYPE_DICOM_RAW_GRANTED, EVENT_TYPE_DICOM_RAW_REVOKED)] == [
        EVENT_TYPE_DICOM_RAW_GRANTED, EVENT_TYPE_DICOM_RAW_REVOKED]


@pytest.mark.django_db
def test_changing_the_site_is_audited_and_the_project_never_changes(project):
    binding = _bound(project)
    other = ResearchProject.objects.create(name="Other", description="")

    _admin(project).post(
        _url("dashboard_tab_api_client_update", project, binding.id),
        {"clinic": str(_site("B").id), "research_project": str(other.id)}, **HTMX)

    binding.refresh_from_db()
    assert binding.clinic == _site("B")
    assert binding.research_project == project
    (updated,) = _events(EVENT_TYPE_API_CLIENT_UPDATED)
    assert updated.metadata["clinic_id"] == str(_site("B").id)


@pytest.mark.django_db
def test_rotating_replaces_the_secret_and_ends_issued_tokens(project):
    admin = _admin(project)
    old_secret = _secret_in(_issue(admin, project))
    binding = ClientBinding.objects.get()
    assert _token_status(binding.application, old_secret) == 200

    new_secret = _secret_in(admin.post(_url("dashboard_tab_api_client_rotate", project, binding.id), **HTMX))

    assert new_secret != old_secret
    assert not AccessToken.objects.filter(application=binding.application).exists()
    assert _token_status(binding.application, old_secret) == 401
    assert _token_status(binding.application, new_secret) == 200
    assert len(_events(EVENT_TYPE_API_CLIENT_SECRET_ROTATED)) == 1


@pytest.mark.django_db
def test_revoking_removes_the_client_and_its_tokens(project):
    admin = _admin(project)
    secret = _secret_in(_issue(admin, project, dicom_raw=True))
    binding = ClientBinding.objects.get()
    application = binding.application
    client_id = application.client_id

    response = admin.post(_url("dashboard_tab_api_client_revoke", project, binding.id), **HTMX)

    assert response.status_code == 200
    assert not ClientBinding.objects.exists()
    assert not Application.objects.filter(client_id=client_id).exists()
    assert not AccessToken.objects.exists()
    assert _token_status(application, secret) == 401
    (revoked,) = _events(EVENT_TYPE_API_CLIENT_REVOKED)
    assert revoked.metadata["client_id"] == client_id
    assert len(_events(EVENT_TYPE_DICOM_RAW_REVOKED)) == 1


@pytest.mark.django_db
def test_changes_need_a_post(project):
    binding = _bound(project)

    response = _admin(project).get(_url("dashboard_tab_api_client_revoke", project, binding.id), **HTMX)

    assert response.status_code == 405
    assert ClientBinding.objects.filter(pk=binding.pk).exists()

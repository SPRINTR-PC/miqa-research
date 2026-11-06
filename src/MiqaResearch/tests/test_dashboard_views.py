import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client

from MiqaResearch.data.models import ResearchProject, ResearchProjectRole, ResearchProjectUserRoleMap

User = get_user_model()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="researcher", email="researcher@example.com", password="password")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other", email="other@example.com", password="password")


@pytest.fixture
def role(db):
    return ResearchProjectRole.objects.get_or_create(
        name="Investigator", defaults={"description": "Investigator role"})[0]


@pytest.fixture
def project_a(db):
    return ResearchProject.objects.create(name="PROTECT-RT", description="Proton therapy outcomes registry")


@pytest.fixture
def project_b(db):
    return ResearchProject.objects.create(name="ARC-Prostate", description="Adaptive radiotherapy cohort")


def _involve(user, project, role):
    return ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path_template",
    [
        "/dashboard/",
        "/dashboard/{project_id}/",
        "/dashboard/{project_id}/tabs/consent-statistics/",
        "/dashboard/{project_id}/tabs/goals/",
        "/administration/",
        "/monitor/",
        "/upload/",
    ],
)
def test_anonymous_request_redirects_to_login(client, project_a, path_template):
    response = client.get(path_template.format(project_id=project_a.id))

    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/")


@pytest.mark.django_db
def test_dashboard_redirects_to_single_project(client, user, role, project_a):
    _involve(user, project_a, role)
    client.force_login(user)

    response = client.get("/dashboard/")

    assert response.status_code == 302
    assert response["Location"] == f"/dashboard/{project_a.id}/"


@pytest.mark.django_db
def test_dashboard_renders_empty_state_for_zero_involvements(client, user):
    client.force_login(user)

    response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "You are not yet part of any research project" in response.content.decode()


@pytest.mark.django_db
def test_dashboard_renders_grid_for_multiple_involvements(client, user, role, project_a, project_b):
    _involve(user, project_a, role)
    _involve(user, project_b, role)
    client.force_login(user)

    response = client.get("/dashboard/")
    content = response.content.decode()

    assert response.status_code == 200
    assert project_a.name in content
    assert project_b.name in content


@pytest.mark.django_db
def test_project_dashboard_404_for_uninvolved_user(client, user, project_a):
    client.force_login(user)

    response = client.get(f"/dashboard/{project_a.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_project_dashboard_renders_shell_with_default_tab(client, user, role, project_a):
    _involve(user, project_a, role)
    client.force_login(user)

    response = client.get(f"/dashboard/{project_a.id}/")
    content = response.content.decode()

    assert response.status_code == 200
    assert project_a.name in content
    assert project_a.description in content
    assert "<mires-chart-bar" in content
    assert 'aria-selected="true"' in content


@pytest.mark.django_db
def test_goals_tab_htmx_returns_bare_partial(client, user, role, project_a):
    _involve(user, project_a, role)
    client.force_login(user)

    response = client.get(f"/dashboard/{project_a.id}/tabs/goals/", HTTP_HX_REQUEST="true")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Data collection goals content will appear here." in content
    assert "<nav" not in content


@pytest.mark.django_db
def test_goals_tab_non_htmx_returns_full_shell(client, user, role, project_a):
    _involve(user, project_a, role)
    client.force_login(user)

    response = client.get(f"/dashboard/{project_a.id}/tabs/goals/")
    content = response.content.decode()

    assert response.status_code == 200
    assert project_a.name in content
    assert "Data collection goals content will appear here." in content


@pytest.mark.django_db
def test_tab_endpoint_anonymous_htmx_returns_hx_redirect_header(client, project_a):
    response = client.get(f"/dashboard/{project_a.id}/tabs/consent-statistics/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert response["HX-Redirect"].startswith("/accounts/login/")


def test_icon_classes_reach_both_wrapper_and_svg():
    html = render_to_string("components/icon.html", {"icon_name": "target", "icon_classes": "my-test-icon-class"})

    wrapper_div, svg_tag = html.split("<svg", 1)[0], html.split("<svg", 1)[1].split(">", 1)[0]

    assert "my-test-icon-class" in wrapper_div
    assert "my-test-icon-class" in svg_tag

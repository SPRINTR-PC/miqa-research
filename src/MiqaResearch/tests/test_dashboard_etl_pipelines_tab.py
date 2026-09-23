"""
ETL Pipelines dashboard tab (wayfinder #150): a third project tab with a section sidebar
(Bindings/Scripts/Jobs/Defaults). Navigation/rendering structure for an Admin, who can see every
section's empty state and (Bindings/Scripts/Defaults) its manage controls; Jobs stays an empty
state -- it's wired once Jobs exist (wayfinder ticket 8). Role-boundary and manage-action behavior
live in test_etl_permissions.py and the section-specific test_dashboard_etl_*.py files. Driven
through the real views, as consent statistics and goals are in test_dashboard_tabs.py.
"""
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from MiqaResearch.data.models import ResearchProject, ResearchProjectRole, ResearchProjectUserRoleMap

User = get_user_model()

SECTIONS = ["bindings", "scripts", "jobs", "defaults"]
SECTION_ICON = {
    "bindings": ">No pipelines connected yet<",
    "scripts": ">No scripts registered yet<",
    "jobs": ">No jobs yet<",
    "defaults": ">No built-in scripts registered yet<",
}

HTMX = {"HTTP_HX_REQUEST": "true"}
HISTORY_RESTORE = {"HTTP_HX_REQUEST": "true", "HTTP_HX_HISTORY_RESTORE_REQUEST": "true"}


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="ETL Tabs Project", description="desc")


@pytest.fixture
def client(db, project):
    user = User.objects.create_user(username="etl-tabs-user", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name="Admin", defaults={"description": "Admin"})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    client = Client()
    client.force_login(user)
    return client


def _tab_url(project):
    return reverse("dashboard_tab_etl_pipelines", args=[project.id])


def _content_url(project, section=None):
    url = reverse("dashboard_tab_etl_pipelines_content", args=[project.id])
    return f"{url}?section={section}" if section else url


def _selected_main_tab(body: str) -> str | None:
    match = re.search(r'aria-selected="true"[^>]*>.*?ETL Pipelines', body, re.DOTALL)
    return "ETL Pipelines" if match else None


def _active_sidebar_link(body: str) -> str | None:
    match = re.search(r'class="etl-sidebar-link active"[^>]*>(?:\s*<[^>]+>)*\s*([A-Za-z]+)', body)
    return match.group(1) if match else None


# --- Full page loads ------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_full_page_defaults_to_the_bindings_section(client, project):
    response = client.get(_tab_url(project))
    body = response.content.decode()

    assert _selected_main_tab(body) == "ETL Pipelines"
    assert _active_sidebar_link(body) == "Bindings"
    assert SECTION_ICON["bindings"] in body
    assert "etl-sidebar" in body


@pytest.mark.django_db
@pytest.mark.parametrize("section", SECTIONS)
def test_full_page_for_each_section_highlights_it_and_shows_its_empty_state(client, project, section):
    body = client.get(_content_url(project, section)).content.decode()

    assert _active_sidebar_link(body) == section.capitalize()
    assert SECTION_ICON[section] in body


@pytest.mark.django_db
def test_history_restore_after_a_cache_miss_gets_a_full_page(client, project):
    response = client.get(_content_url(project, "jobs"), **HISTORY_RESTORE)

    assert "<html" in response.content.decode()
    assert _active_sidebar_link(response.content.decode()) == "Jobs"


# --- htmx section switches ------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("section", SECTIONS)
def test_switching_sections_returns_the_section_panel_and_highlights_it_out_of_band(client, project, section):
    response = client.get(_content_url(project, section), **HTMX)
    body = response.content.decode()

    assert SECTION_ICON[section] in body
    assert 'id="etl-sidebar"' in body and 'hx-swap-oob="true"' in body
    assert _active_sidebar_link(body) == section.capitalize()
    # the main tablist is also re-sent out of band, so a direct section link keeps ETL Pipelines highlighted
    assert 'id="dashboard-tablist"' in body and _selected_main_tab(body) == "ETL Pipelines"


@pytest.mark.django_db
def test_switching_to_the_etl_pipelines_tab_defaults_to_bindings(client, project):
    body = client.get(_tab_url(project), **HTMX).content.decode()

    assert _active_sidebar_link(body) == "Bindings"
    assert SECTION_ICON["bindings"] in body


# --- Binding wizard ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_bindings_section_shows_a_working_wizard_behind_a_disclosure_for_a_manager(client, project):
    body = client.get(_content_url(project, "bindings")).content.decode()

    assert "New binding" in body
    assert "etl-wizard" in body
    button = re.search(r'<button class="btn" type="submit">.*?Create binding.*?</button>', body, re.DOTALL)
    assert button is not None
    assert "disabled" not in button.group(0)


@pytest.mark.django_db
def test_every_sidebar_link_names_a_loading_indicator_that_exists_on_the_page(client, project):
    body = client.get(_tab_url(project)).content.decode()
    refs = re.findall(r'hx-indicator="([^"]+)"', body)

    sidebar_refs = [ref for ref in refs if "etl-section-panel" in ref]
    assert len(sidebar_refs) == 4  # Bindings, Scripts, Jobs, Defaults
    for reference in sidebar_refs:
        for selector in (part.strip() for part in reference.split(",")):
            assert selector.startswith("#")
            assert f'id="{selector[1:]}"' in body, f"{selector} is not on the page"

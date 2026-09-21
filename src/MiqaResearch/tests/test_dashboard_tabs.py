"""
Consent dashboard tabs and sub-tabs: the active one is always the one highlighted, and every tab switch shows a loading
indicator. Driven through the real views with the Django test client, as a browser (full page) or htmx would.
"""
import re
from html.parser import HTMLParser

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from MiqaResearch.data.models import ResearchProject, ResearchProjectRole, ResearchProjectUserRoleMap

User = get_user_model()

TABLIST_IDS = ("dashboard-tablist", "dashboard-consent-tablist")


class _Tablists(HTMLParser):
    """Collects, per tablist id, the (label, aria-selected) of its tab buttons, and the ids present in the markup."""

    def __init__(self):
        super().__init__()
        self.tablists: dict[str, list[tuple[str, bool]]] = {}
        self.ids: set[str] = set()
        self.oob_ids: set[str] = set()
        self.indicator_refs: list[str] = []
        self.sync_refs: list[str] = []
        self._tablist: str | None = None
        self._tab: list | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
            if "hx-swap-oob" in attributes:
                self.oob_ids.add(attributes["id"])
        if attributes.get("id") in TABLIST_IDS:
            self._tablist = attributes["id"]
            self.tablists[self._tablist] = []
        if tag == "button" and attributes.get("role") == "tab" and self._tablist:
            self._tab = [attributes.get("aria-selected") == "true", ""]
            self.tablists[self._tablist].append(self._tab)
            self.indicator_refs.append(attributes.get("hx-indicator", ""))
            self.sync_refs.append(attributes.get("hx-sync", ""))

    def handle_data(self, data):
        if self._tab is not None:
            self._tab[1] += data

    def handle_endtag(self, tag):
        if tag == "button":
            self._tab = None

    def selected(self, tablist_id):
        return [label.strip() for is_selected, label in self.tablists[tablist_id] if is_selected]


def parse(response) -> _Tablists:
    parser = _Tablists()
    parser.feed(response.content.decode())
    return parser


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Tabs Project", description="desc")


@pytest.fixture
def client(db, project):
    user = User.objects.create_user(username="tabs-user", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name="Admin", defaults={"description": "Admin"})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    client = Client()
    client.force_login(user)
    return client


def _url(project, tab, table=False):
    name = {
        "consent": "dashboard_tab_consent_statistics",
        "content": "dashboard_tab_consent_statistics_content",
        "goals": "dashboard_tab_goals",
    }[tab]
    return reverse(name, args=[project.id]) + ("?table=true" if table else "")


HTMX = {"HTTP_HX_REQUEST": "true"}
HISTORY_RESTORE = {"HTTP_HX_REQUEST": "true", "HTTP_HX_HISTORY_RESTORE_REQUEST": "true"}


# --- Full page loads (first visit, reload, or a pushed URL) ---------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("tab", ["consent", "content"])
def test_full_page_defaults_to_the_plots_subtab_with_the_plots_panel(client, project, tab):
    response = client.get(_url(project, tab))
    page = parse(response)

    assert page.selected("dashboard-tablist") == ["Consent Statistics"]
    assert page.selected("dashboard-consent-tablist") == ["Plots"]
    assert "<mires-chart-bar" in response.content.decode()
    assert "<data-table" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("tab", ["consent", "content"])
def test_full_page_for_the_table_subtab_highlights_it_and_renders_the_table_panel(client, project, tab):
    response = client.get(_url(project, tab, table=True))
    page = parse(response)

    assert page.selected("dashboard-tablist") == ["Consent Statistics"]
    assert page.selected("dashboard-consent-tablist") == ["Table"]
    assert "<data-table" in response.content.decode()
    assert "<mires-chart-bar" not in response.content.decode()


@pytest.mark.django_db
def test_full_page_goals_highlights_only_the_goals_tab_and_has_no_subtabs(client, project):
    page = parse(client.get(_url(project, "goals")))

    assert page.selected("dashboard-tablist") == ["Goals"]
    assert "dashboard-consent-tablist" not in page.tablists


# --- htmx tab switches --------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("table, expected", [(False, "Plots"), (True, "Table")])
def test_switching_to_a_subtab_updates_the_subtab_highlight_out_of_band(client, project, table, expected):
    response = client.get(_url(project, "content", table=table), **HTMX)
    page = parse(response)

    assert page.selected("dashboard-consent-tablist") == [expected]
    assert "dashboard-consent-tablist" in page.oob_ids  # the sub tab list is not the swap target, so it must be OOB
    assert page.selected("dashboard-tablist") == ["Consent Statistics"]
    assert "dashboard-tablist" in page.oob_ids


@pytest.mark.django_db
def test_switching_to_the_table_subtab_returns_only_the_table_panel(client, project):
    body = client.get(_url(project, "content", table=True), **HTMX).content.decode()

    assert "<data-table" in body and "<mires-chart-bar" not in body


@pytest.mark.django_db
@pytest.mark.parametrize("table, expected, panel", [(False, "Plots", "<mires-chart-bar"), (True, "Table", "<data-table")])
def test_switching_to_the_consent_tab_highlights_the_subtab_and_renders_its_panel(client, project, table, expected, panel):
    response = client.get(_url(project, "consent", table=table), **HTMX)
    page = parse(response)

    assert page.selected("dashboard-consent-tablist") == [expected]
    assert page.selected("dashboard-tablist") == ["Consent Statistics"]
    assert panel in response.content.decode()


@pytest.mark.django_db
def test_switching_to_goals_highlights_goals_only(client, project):
    page = parse(client.get(_url(project, "goals"), **HTMX))

    assert page.selected("dashboard-tablist") == ["Goals"]
    assert "dashboard-consent-tablist" not in page.tablists


@pytest.mark.django_db
def test_history_restore_after_a_cache_miss_gets_a_full_page_not_a_partial(client, project):
    """htmx swaps a history-restore response into the whole body, so a partial there would break the page."""
    response = client.get(_url(project, "content", table=True), **HISTORY_RESTORE)

    assert "<html" in response.content.decode()
    assert parse(response).selected("dashboard-consent-tablist") == ["Table"]


@pytest.mark.django_db
def test_goals_history_restore_after_a_cache_miss_gets_a_full_page(client, project):
    response = client.get(_url(project, "goals"), **HISTORY_RESTORE)

    assert "<html" in response.content.decode()
    assert parse(response).selected("dashboard-tablist") == ["Goals"]


# --- Loading indicator ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_tab_and_subtab_button_names_a_loading_indicator_that_exists_on_the_page(client, project):
    page = parse(client.get(_url(project, "consent")))

    assert len(page.indicator_refs) == 4  # two tabs and two subtabs
    for reference in page.indicator_refs:
        assert reference, "a tab button without an hx-indicator"
        for selector in (part.strip() for part in reference.split(",")):
            assert selector.startswith("#") and selector[1:] in page.ids, f"{selector} is not on the page"


@pytest.mark.django_db
def test_tab_buttons_replace_an_in_flight_switch_so_a_late_response_cannot_win(client, project):
    page = parse(client.get(_url(project, "consent")))

    assert page.sync_refs == ["#dashboard-tab-panel:replace"] * 4
    assert "dashboard-tab-panel" in page.ids


@pytest.mark.django_db
def test_the_indicators_are_status_regions_that_stay_outside_the_swapped_content(client, project):
    body = client.get(_url(project, "consent")).content.decode()

    for indicator_id in ("dashboard-tab-loading", "dashboard-consent-loading"):
        element = re.search(rf'<[^>]*id="{indicator_id}"[^>]*>', body)
        assert element, indicator_id
        assert "htmx-indicator" in element.group(0) and 'role="status"' in element.group(0)
    # the main indicator sits outside #dashboard-tab-panel and the sub indicator outside #dashboard-consent-contents
    assert body.index("dashboard-tab-loading") < body.index('id="dashboard-tab-panel"')
    assert body.index("dashboard-consent-loading") < body.index('id="dashboard-consent-contents"')


@pytest.mark.django_db
def test_the_panels_being_replaced_are_dimmed_while_loading(client, project):
    body = client.get(_url(project, "consent")).content.decode()

    for panel_id in ("dashboard-tab-panel", "dashboard-consent-contents"):
        element = re.search(rf'<[^>]*id="{panel_id}"[^>]*>', body)
        assert element and "loading-target" in element.group(0), panel_id


# --- PID checkbox --------------------------------------------------------------------------------------------------

PID_CHECKBOX = 'id="consent-table-include-pid"'


def _client_with_role(project, role_name):
    user = User.objects.create_user(username=f"pid-{role_name}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ["Admin", "PI", "Participant Recruiter"])
@pytest.mark.parametrize("request_kwargs", [{}, HTMX])
@pytest.mark.parametrize("tab", ["consent", "content"])
def test_pid_checkbox_is_shown_above_the_table_to_roles_that_may_view_pid(project, role_name, request_kwargs, tab):
    response = _client_with_role(project, role_name).get(_url(project, tab, table=True), **request_kwargs)

    assert PID_CHECKBOX in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("request_kwargs", [{}, HTMX])
def test_pid_checkbox_is_hidden_from_roles_that_may_not_view_pid(project, request_kwargs):
    response = _client_with_role(project, "Investigator").get(_url(project, "content", table=True), **request_kwargs)

    assert "<data-table" in response.content.decode()
    assert PID_CHECKBOX not in response.content.decode()


@pytest.mark.django_db
def test_pid_checkbox_is_not_on_the_plots_subtab(client, project):
    assert PID_CHECKBOX not in client.get(_url(project, "content")).content.decode()

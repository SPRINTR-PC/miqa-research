"""In-app manual pages, served from the hand-written fixture build."""

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

FIXTURE_BUILD_DIR = Path(__file__).resolve().parent / "fixtures" / "manuals"

User = get_user_model()


@pytest.fixture(autouse=True)
def _fixture_build(settings):
    settings.MANUALS_BUILD_DIR = FIXTURE_BUILD_DIR


@pytest.fixture
def member(db):
    return User.objects.create_user(username="member", password="password")


@pytest.fixture
def member_client(member):
    client = Client()
    client.force_login(member)
    return client


def test_signed_in_user_reads_user_manual_inside_app_shell(member_client):
    response = member_client.get("/manuals/user/")

    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="mires-main"' in html
    assert "Welcome to the fixture user manual." in html


def test_nested_page_is_served_at_its_language_neutral_url(member_client):
    response = member_client.get("/manuals/user/guide/getting-started/")

    assert response.status_code == 200
    assert "Sign in to start working." in response.content.decode()


def test_index_url_redirects_to_manual_root(member_client):
    response = member_client.get("/manuals/user/index/")

    assert response.status_code == 301
    assert response["Location"] == "/manuals/user/"


def test_manuals_root_redirects_to_user_manual(member_client):
    response = member_client.get("/manuals/")

    assert response.status_code == 302
    assert response["Location"] == "/manuals/user/"


@pytest.mark.parametrize("url", ["/manuals/user/no-such-page/", "/manuals/no-such-manual/"])
def test_unknown_manual_or_page_is_404(member_client, url):
    assert member_client.get(url).status_code == 404


def _client_for(**flags):
    client = Client()
    client.force_login(User.objects.create_user(username="u-" + ("-".join(flags) or "member"), **flags))
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flags", "status"),
    [({}, 404), ({"is_staff": True}, 200), ({"is_superuser": True}, 200)],
    ids=["member", "staff-user", "superuser"],
)
def test_technical_manual_is_only_for_superusers_and_staff_users(flags, status):
    client = _client_for(**flags)

    assert client.get("/manuals/technical/").status_code == status
    assert client.get("/manuals/technical/no-such-page/").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/manuals/user/", "/manuals/technical/", "/manuals/technical/no-such-page/"])
def test_anonymous_visitor_is_redirected_to_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/?next=")


@pytest.mark.parametrize("url", ["/manuals/user/search/", "/manuals/user/genindex/"])
def test_sphinx_search_and_genindex_pages_are_not_served(member_client, url):
    assert member_client.get(url).status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "/manuals/user/../technical/",
        "/manuals/user/%2e%2e/technical/",
        "/manuals/user/guide/..%2f..%2ftechnical/en/index/",
        "/manuals/user//etc/passwd/",
        "/manuals/user/%2Fetc%2Fpasswd/",
        "/manuals/user/index.fjson/",
    ],
)
def test_path_traversal_is_rejected(member_client, url):
    assert member_client.get(url).status_code == 404


UNTRANSLATED_NOTICE = "Parts of this page are not yet translated"


@pytest.fixture
def swedish_and_german(settings):
    settings.LANGUAGES = [("en", "English"), ("sv", "Svenska"), ("de", "Deutsch")]


@pytest.mark.usefixtures("swedish_and_german")
def test_partly_translated_page_is_served_in_active_language_with_notice(member_client):
    html = member_client.get("/manuals/user/", HTTP_ACCEPT_LANGUAGE="sv").content.decode()

    assert "Välkommen till fixture-användarmanualen." in html
    assert UNTRANSLATED_NOTICE in html


@pytest.mark.usefixtures("swedish_and_german")
def test_fully_translated_page_has_no_notice(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/", HTTP_ACCEPT_LANGUAGE="sv").content.decode()

    assert "Logga in för att börja arbeta." in html
    assert UNTRANSLATED_NOTICE not in html


@pytest.mark.usefixtures("swedish_and_german")
@pytest.mark.parametrize("language", ["de", "en"])
def test_language_without_build_falls_back_to_english_without_notice(member_client, language):
    html = member_client.get("/manuals/user/", HTTP_ACCEPT_LANGUAGE=language).content.decode()

    assert "Welcome to the fixture user manual." in html
    assert UNTRANSLATED_NOTICE not in html


def _manual_nav(html):
    """The navbar's manual control, from id="nav-manual" to the theme toggle."""
    start = html.find('id="nav-manual"')
    return html[start : html.index('id="theme-toggle-btn"')] if start != -1 else ""


@pytest.mark.django_db
@pytest.mark.parametrize("flags", [{"is_staff": True}, {"is_superuser": True}], ids=["staff-user", "superuser"])
def test_navbar_offers_both_manuals_to_superusers_and_staff_users(flags):
    nav = _manual_nav(_client_for(**flags).get("/").content.decode())

    assert 'class="nav-dropdown"' in nav
    assert 'href="/manuals/user/"' in nav
    assert 'href="/manuals/technical/"' in nav


def test_navbar_links_other_users_straight_to_user_manual(member_client):
    nav = _manual_nav(member_client.get("/").content.decode())

    assert 'href="/manuals/user/"' in nav
    assert "/manuals/technical/" not in nav
    assert "nav-dropdown" not in nav


@pytest.mark.django_db
def test_navbar_hides_manual_button_from_anonymous_visitors(client):
    html = client.get("/").content.decode()

    assert 'id="theme-toggle-btn"' in html
    assert _manual_nav(html) == ""

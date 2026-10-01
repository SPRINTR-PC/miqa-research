"""In-app manual search over the build-time search.json, served from the fixture build."""

import json
import re
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
def member_client(db):
    client = Client()
    client.force_login(User.objects.create_user(username="member"))
    return client


def result_titles(response):
    return re.findall(r'class="manual-search-title">([^<]*)<', response.content.decode())


def test_title_hit_ranks_above_body_hit(member_client):
    response = member_client.get("/manuals/user/search/", {"q": "project"})

    assert response.status_code == 200
    assert result_titles(response) == ["Project settings", "Next steps"]


def test_every_word_must_match(member_client):
    assert result_titles(member_client.get("/manuals/user/search/", {"q": "project rename"})) == ["Project settings"]
    assert result_titles(member_client.get("/manuals/user/search/", {"q": "project nowhere"})) == []


def test_matching_ignores_case_and_accents(member_client):
    assert result_titles(member_client.get("/manuals/user/search/", {"q": "RESUME"})) == ["Exporting results"]
    assert result_titles(member_client.get("/manuals/user/search/", {"q": "résumé"})) == ["Exporting results"]


def result_snippets(response):
    return re.findall(r'class="manual-search-snippet">(.*?)</span>', response.content.decode(), re.S)


def test_snippet_marks_the_terms_and_escapes_html(member_client):
    response = member_client.get("/manuals/user/search/", {"q": "export resume"})

    (snippet,) = result_snippets(response)
    assert "<mark>Export</mark> a <mark>résumé</mark> of the study." in snippet
    assert "&lt;<mark>Export</mark>&gt; button &amp; wait." in snippet
    assert "<Export>" not in snippet


def test_technical_manual_search_is_404_for_users_who_are_neither_superuser_nor_staff(member_client):
    assert member_client.get("/manuals/technical/search/", {"q": "deployment"}).status_code == 404


def test_staff_user_searches_the_technical_manual_only(db):
    client = Client()
    client.force_login(User.objects.create_user(username="staff", is_staff=True))

    assert result_titles(client.get("/manuals/technical/search/", {"q": "deployment"})) == ["Fixture Technical Manual"]
    assert result_titles(client.get("/manuals/technical/search/", {"q": "project"})) == []


def test_anonymous_visitor_is_redirected_to_login(client):
    response = client.get("/manuals/user/search/", {"q": "project"})

    assert response.status_code == 302
    assert "login" in response["Location"]


def test_active_language_searches_its_own_index(settings, member_client):
    settings.LANGUAGES = [("en", "English"), ("sv", "Svenska")]

    assert result_titles(member_client.get("/manuals/user/search/", {"q": "välkommen"}, HTTP_ACCEPT_LANGUAGE="sv")) == [
        "Fixture-användarmanual"
    ]
    assert result_titles(member_client.get("/manuals/user/search/", {"q": "välkommen"})) == []


def test_unknown_manual_search_is_404(member_client):
    assert member_client.get("/manuals/nope/search/", {"q": "project"}).status_code == 404


def test_result_links_to_the_section_on_its_page(member_client):
    html = member_client.get("/manuals/user/search/", {"q": "rename"}).content.decode()

    assert 'href="/manuals/user/guide/getting-started/#project-settings"' in html


def test_live_panel_returns_at_most_eight_results(settings, tmp_path, member_client):
    index = tmp_path / "user" / "en" / "search.json"
    index.parent.mkdir(parents=True)
    entries = [
        {"page": "index", "anchor": f"s{i}", "title": f"Section {i}", "breadcrumb": [], "text": "Shared."}
        for i in range(10)
    ]
    index.write_text(json.dumps(entries))
    settings.MANUALS_BUILD_DIR = tmp_path

    response = member_client.get("/manuals/user/search/live/", {"q": "shared"})

    assert response.status_code == 200
    assert result_titles(response) == [f"Section {i}" for i in range(8)]
    assert "<html" not in response.content.decode()


def test_live_panel_shows_breadcrumb_and_snippet(member_client):
    html = member_client.get("/manuals/user/search/live/", {"q": "rename"}).content.decode()

    assert re.search(r'class="manual-search-breadcrumb">\s*Getting started\s*<', html)
    assert "<mark>Rename</mark> or archive a project." in html


def test_live_panel_is_empty_below_two_characters(member_client):
    response = member_client.get("/manuals/user/search/live/", {"q": "p"})

    assert response.status_code == 200
    assert response.content.decode().strip() == ""


def test_live_panel_follows_manual_access(member_client):
    assert member_client.get("/manuals/technical/search/live/", {"q": "deployment"}).status_code == 404


def test_search_input_drives_the_live_panel_and_submits_to_the_results_page(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/").content.decode()

    form = re.search(r'<form\b[^>]*class="manual-search"[^>]*>.*?</form>', html, re.S).group(0)
    assert 'action="/manuals/user/search/"' in form
    search_input = re.search(r'<input\b[^>]*name="q"[^>]*>', form).group(0)
    assert 'hx-get="/manuals/user/search/live/"' in search_input
    assert 'hx-trigger="input changed delay:300ms, search"' in search_input
    assert 'hx-target="#manual-search-panel"' in search_input
    assert 'id="manual-search-panel"' in form


def test_result_on_the_manual_root_links_to_the_manual_url(member_client):
    html = member_client.get("/manuals/user/search/", {"q": "welcome"}).content.decode()

    assert 'href="/manuals/user/#fixture-user-manual"' in html

"""Variant-B manual layout: top bar, Contents drawer, On this page, pager, mermaid."""

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


def _signed_in(**flags):
    client = Client()
    client.force_login(User.objects.create_user(username="u-" + ("-".join(flags) or "member"), **flags))
    return client


@pytest.fixture
def member_client(db):
    return _signed_in()


@pytest.fixture
def staff_client(db):
    return _signed_in(is_staff=True)


def _element(html, tag, marker):
    """The first ``<tag ...marker...>...</tag>`` in ``html`` (no nesting of the same tag)."""
    match = re.search(rf"<{tag}\b[^>]*{re.escape(marker)}[^>]*>.*?</{tag}>", html, re.S)
    return match.group(0) if match else ""


def test_contents_drawer_holds_the_manual_toctree(member_client):
    html = member_client.get("/manuals/user/").content.decode()

    drawer = _element(html, "dialog", 'id="manual-contents"')
    assert 'href="guide/getting-started/"' in drawer
    assert 'aria-controls="manual-contents"' in html


def test_breadcrumb_leads_from_manual_to_page(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/").content.decode()

    crumbs = _element(html, "nav", 'class="manual-breadcrumb"')
    assert re.search(r'<a href="/manuals/user/">\s*User Manual\s*</a>', crumbs)
    assert crumbs.index("User Manual") < crumbs.index("Getting started")


def test_breadcrumb_on_manual_root_shows_only_the_manual(member_client):
    crumbs = _element(member_client.get("/manuals/user/").content.decode(), "nav", 'class="manual-breadcrumb"')

    assert "User Manual" in crumbs
    assert "Fixture User Manual" not in crumbs


def test_manual_switch_is_offered_to_superusers_and_staff_users(staff_client):
    html = staff_client.get("/manuals/user/").content.decode()

    switch = _element(html, "nav", 'class="manual-switch"')
    assert 'href="/manuals/user/" aria-current="true"' in switch
    assert 'href="/manuals/technical/"' in switch


def test_manual_switch_is_absent_for_other_users(member_client):
    assert 'class="manual-switch"' not in member_client.get("/manuals/user/").content.decode()


def test_on_this_page_box_lists_page_sections_when_display_toc_is_set(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/").content.decode()

    box = _element(html, "details", 'class="manual-on-this-page"')
    assert "On this page" in box
    assert 'href="#next-steps"' in box


def test_on_this_page_box_is_absent_without_display_toc(member_client):
    assert "manual-on-this-page" not in member_client.get("/manuals/user/").content.decode()


@pytest.mark.usefixtures("db")
def test_untranslated_notice_sits_between_top_bar_and_page(settings, member_client):
    settings.LANGUAGES = [("en", "English"), ("sv", "Svenska")]
    html = member_client.get("/manuals/user/", HTTP_ACCEPT_LANGUAGE="sv").content.decode()

    assert html.index('class="manual-bar"') < html.index("manual-untranslated-notice") < html.index("manual-prose")


def test_pager_links_to_next_page(member_client):
    pager = _element(member_client.get("/manuals/user/").content.decode(), "nav", 'class="manual-pager"')

    assert re.search(r'<a class="manual-pager-next" href="guide/getting-started/">.*Getting started', pager, re.S)
    assert "manual-pager-prev" not in pager


def test_pager_links_to_previous_page(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/").content.decode()
    pager = _element(html, "nav", 'class="manual-pager"')

    assert re.search(r'<a class="manual-pager-prev" href="../../">.*Fixture User Manual', pager, re.S)
    assert "manual-pager-next" not in pager


def test_manual_page_loads_mermaid_and_keeps_mermaid_containers(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/").content.decode()

    assert re.search(r'<script src="[^"]*js/mermaid\.min\.js"', html)
    assert re.search(r'<script src="[^"]*js/manuals\.js"', html)
    assert '<pre  class="mermaid">' in html


def test_other_app_pages_do_not_load_mermaid(member_client):
    html = member_client.get("/").content.decode()

    assert "mermaid.min.js" not in html
    assert "manuals.js" not in html

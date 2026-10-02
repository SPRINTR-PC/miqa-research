"""Help Links: the manual_link tag and manual_url helper, resolved against the fixture build's labels.json."""

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.test import RequestFactory
from django.utils import translation

from documentation.help_links import UnknownHelpLink, manual_url

FIXTURE_BUILD_DIR = Path(__file__).resolve().parent / "fixtures" / "manuals"

User = get_user_model()


@pytest.fixture(autouse=True)
def _fixture_build(settings):
    settings.MANUALS_BUILD_DIR = FIXTURE_BUILD_DIR


def request_for(user):
    request = RequestFactory().get("/dashboard/")
    request.user = user
    return request


@pytest.fixture
def member(db):
    return User.objects.create_user(username="member")


def render(source, user):
    return Template("{% load manuals %}" + source).render(Context({"request": request_for(user)}))


def test_help_link_renders_a_question_mark_button_to_the_labelled_section(member):
    html = render('{% manual_link "user" "app-fixture-getting-started" %}', member)

    assert 'href="/manuals/user/guide/getting-started/#app-fixture-getting-started"' in html
    assert 'target="_blank" rel="noopener"' in html
    assert 'aria-label="Help: Getting started"' in html
    assert 'title="Help: Getting started"' in html
    assert ">?</a>" in html


def test_help_link_is_empty_for_anonymous_visitors(db):
    assert render('{% manual_link "user" "app-fixture-getting-started" %}', AnonymousUser()) == ""


def test_technical_manual_help_link_is_empty_unless_superuser_or_staff_user(member):
    source = '{% manual_link "technical" "app-fixture-operations" %}'
    staff = User.objects.create_user(username="staff", is_staff=True)
    superuser = User.objects.create_user(username="root", is_superuser=True)

    assert render(source, member) == ""
    assert 'href="/manuals/technical/#app-fixture-operations"' in render(source, staff)
    assert 'href="/manuals/technical/#app-fixture-operations"' in render(source, superuser)


def test_unknown_label_raises_in_debug(settings, member):
    settings.DEBUG = True

    with pytest.raises(UnknownHelpLink):
        render('{% manual_link "user" "app-no-such-label" %}', member)


def test_unknown_label_logs_a_warning_and_renders_nothing_outside_debug(settings, member, caplog):
    settings.DEBUG = False

    assert render('{% manual_link "user" "app-no-such-label" %}', member) == ""
    assert "app-no-such-label" in caplog.text


def test_missing_labels_json_raises_in_debug(settings, tmp_path, member):
    settings.DEBUG = True
    settings.MANUALS_BUILD_DIR = tmp_path

    with pytest.raises(UnknownHelpLink):
        render('{% manual_link "user" "app-fixture-getting-started" %}', member)


def test_unknown_manual_raises_in_debug(settings, member):
    settings.DEBUG = True

    with pytest.raises(UnknownHelpLink):
        render('{% manual_link "nope" "app-fixture-getting-started" %}', member)


def test_text_renders_an_inline_link_instead_of_the_button(member):
    html = render('{% manual_link "user" "app-fixture-getting-started" text="How to start" %}', member)

    assert ">How to start</a>" in html
    assert 'target="_blank" rel="noopener"' in html
    assert ">?</a>" not in html


def test_tooltip_uses_the_active_language_title(member):
    with translation.override("sv"):
        html = render('{% manual_link "user" "app-fixture-getting-started" %}', member)

    assert "Kom igång" in html


def test_tooltip_falls_back_to_english_when_the_translation_lacks_the_label(member):
    with translation.override("sv"):
        html = render('{% manual_link "user" "app-fixture-welcome" %}', member)

    assert "Fixture User Manual" in html


def test_manual_url_resolves_to_the_page_and_anchor(member):
    request = request_for(member)

    assert manual_url(request, "user", "app-fixture-getting-started") == (
        "/manuals/user/guide/getting-started/#app-fixture-getting-started"
    )
    assert manual_url(request, "user", "app-fixture-welcome") == "/manuals/user/#app-fixture-welcome"


def test_manual_url_is_none_without_access(member):
    assert manual_url(request_for(member), "technical", "app-fixture-operations") is None


def test_dashboard_shows_the_demo_help_link(member, client):
    client.force_login(member)

    html = client.get("/dashboard/").content.decode()

    assert 'href="/manuals/user/#app-dashboard-overview"' in html
    assert 'aria-label="Help: The Dashboard"' in html

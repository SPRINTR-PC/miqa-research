"""Viewer dev page (#278): temporary, DEBUG-only, login-required host page for the viewer element.

Seam: the HTTP response of `/viewer/dev/`, plus the shared `base.html` layout.
"""
import pytest
from django.contrib.auth import get_user_model

DEV_PAGE = "/viewer/dev/"
VIEWER_BUNDLE = "js/viewer/mireswc-viewer.js"


@pytest.fixture
def no_toolbar(settings):
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def logged_in_client(client, db):
    client.force_login(get_user_model().objects.create_user(username="viewer-dev", password="pw"))
    return client


def test_dev_page_is_404_when_debug_is_off(settings, no_toolbar, logged_in_client):
    settings.DEBUG = False

    assert logged_in_client.get(DEV_PAGE).status_code == 404


def test_dev_page_requires_login(settings, no_toolbar, client, db):
    settings.DEBUG = True

    response = client.get(DEV_PAGE)

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_dev_page_hosts_the_viewer_for_the_requested_series(settings, no_toolbar, logged_in_client):
    settings.DEBUG = True

    response = logged_in_client.get(DEV_PAGE, {"study": "2.25.1", "series": "2.25.2"})

    assert response.status_code == 200
    body = response.content.decode()
    assert VIEWER_BUNDLE in body
    assert 'study-uid="2.25.1"' in body
    assert 'series-uid="2.25.2"' in body


def test_dev_page_escapes_query_params(settings, no_toolbar, logged_in_client):
    settings.DEBUG = True

    body = logged_in_client.get(DEV_PAGE, {"study": '"><script>x</script>', "series": "1"}).content.decode()

    assert "<script>x</script>" not in body


def test_base_layout_never_loads_the_viewer_bundle(settings, no_toolbar, logged_in_client):
    settings.DEBUG = False

    body = logged_in_client.get("/monitor/").content.decode()

    assert "mireswc.js" in body  # sanity: this page renders base.html
    assert "mireswc-viewer" not in body

"""Manual images and downloads, served through the access-checked asset route."""

import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

FIXTURE_BUILD_DIR = Path(__file__).resolve().parent / "fixtures" / "manuals"
DIAGRAM_URL = "/manuals/user/_images/diagram.png"
DOWNLOAD_URL = "/manuals/user/_downloads/3f2a9c0d4b5e6f708192a3b4c5d6e7f8/sample.csv"

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


def _body(response):
    return b"".join(response.streaming_content)


@pytest.mark.parametrize("page_url", ["/manuals/user/", "/manuals/user/guide/getting-started/"])
def test_image_loads_through_its_relative_link(member_client, page_url):
    html = member_client.get(page_url).content.decode()
    src = re.search(r'<img alt="Diagram" src="([^"]+)"', html).group(1)

    response = member_client.get(urljoin(page_url, src))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert _body(response) == (FIXTURE_BUILD_DIR / "user" / "en" / "_images" / "diagram.png").read_bytes()


def _assert_hardened(response):
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "private, max-age=3600"
    assert response["Content-Security-Policy"] == "sandbox"


def test_image_is_served_inline_with_hardening_headers(member_client):
    response = member_client.get(DIAGRAM_URL)

    _assert_hardened(response)
    assert "attachment" not in response.get("Content-Disposition", "")


def test_download_is_served_as_attachment_with_hardening_headers(member_client):
    html = member_client.get("/manuals/user/guide/getting-started/").content.decode()
    assert f'href="../../{DOWNLOAD_URL.removeprefix("/manuals/user/")}"' in html

    response = member_client.get(DOWNLOAD_URL)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == 'attachment; filename="sample.csv"'
    _assert_hardened(response)
    assert _body(response) == b"id,value\n1,42\n"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flags", "status"),
    [({}, 404), ({"is_staff": True}, 200), ({"is_superuser": True}, 200)],
    ids=["member", "staff-user", "superuser"],
)
def test_technical_manual_assets_follow_technical_manual_access(flags, status):
    assert _signed_in(**flags).get("/manuals/technical/_images/architecture.png").status_code == status


@pytest.mark.django_db
@pytest.mark.parametrize("url", [DIAGRAM_URL, DOWNLOAD_URL, "/manuals/technical/_images/architecture.png"])
def test_anonymous_visitor_is_redirected_to_login_for_assets(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/?next=")


@pytest.mark.parametrize(
    "url",
    [
        "/manuals/user/_sources/index.md.txt",
        "/manuals/user/_static/pygments.css",
        "/manuals/user/index.fjson",
        "/manuals/user/environment.pickle",
        "/manuals/user/searchindex.json",
        "/manuals/user/objects.inv",
        "/manuals/user/search.json",
        "/manuals/user/labels.json",
        "/manuals/user/_images/missing.png",
        "/manuals/no-such-manual/_images/diagram.png",
    ],
)
def test_build_internals_and_unknown_files_are_not_served(member_client, url):
    assert member_client.get(url).status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "/manuals/user/_images/../index.fjson",
        "/manuals/user/_images/..%2findex.fjson",
        "/manuals/user/_images/%2e%2e%2f%2e%2e%2ftechnical%2fen%2f_images%2farchitecture.png",
        "/manuals/user/_images/.hidden",
        "/manuals/user/_images/%2Fetc%2Fpasswd",
        "/manuals/user/_downloads/../_sources/index.md.txt",
        "/manuals/user/_downloads/3f2a9c0d4b5e6f708192a3b4c5d6e7f8/../../_sources/index.md.txt",
        "/manuals/user/_downloads/3f2a9c0d4b5e6f708192a3b4c5d6e7f8/..",
    ],
)
def test_asset_path_traversal_is_rejected(member_client, url):
    assert member_client.get(url).status_code == 404


@pytest.fixture
def swedish(settings):
    settings.LANGUAGES = [("en", "English"), ("sv", "Svenska")]


@pytest.mark.usefixtures("swedish")
def test_active_language_asset_is_preferred(member_client):
    response = member_client.get(DIAGRAM_URL, HTTP_ACCEPT_LANGUAGE="sv")

    assert _body(response) == (FIXTURE_BUILD_DIR / "user" / "sv" / "_images" / "diagram.png").read_bytes()


@pytest.mark.usefixtures("swedish")
@pytest.mark.parametrize("url", ["/manuals/user/_images/only-english.png", DOWNLOAD_URL])
def test_swedish_request_falls_back_to_english_asset(member_client, url):
    response = member_client.get(url, HTTP_ACCEPT_LANGUAGE="sv")

    assert response.status_code == 200
    assert _body(response) == (FIXTURE_BUILD_DIR / "user" / "en" / url.removeprefix("/manuals/user/")).read_bytes()

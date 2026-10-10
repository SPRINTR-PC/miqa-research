"""Viewer dev page (#278): temporary, DEBUG-only, login-required host page for the viewer element.

Seam: the HTTP response of `/viewer/dev/`, plus the shared `base.html` layout.
Since #279 it hands the viewer the same JSON series list as the viewer page, built by the same reader.
"""
import json
import re

import pytest
from django.contrib.auth import get_user_model

from MiqaResearch.data.models import DicomSeries, ResearchProject, ResearchProjectRole, ResearchProjectUserRoleMap
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, write_dicom

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


def _series_list(response) -> list[dict]:
    match = re.search(r'<script id="viewer-series" type="application/json">(.*?)</script>', response.content.decode(), re.S)
    assert match, "no series list on the page"
    return json.loads(match.group(1))


def test_dev_page_hosts_the_viewer_for_the_requested_series(settings, no_toolbar, client, ct_series):
    settings.DEBUG = True
    _open_as(client, ct_series, "Annotator")

    response = client.get(DEV_PAGE, {"series": ct_series.series_instance_uid})

    assert response.status_code == 200
    assert VIEWER_BUNDLE in response.content.decode()
    assert 'series-list="viewer-series"' in response.content.decode()
    assert _series_list(response) == [{
        "study": ct_series.study.study_instance_uid,
        "series": ct_series.series_instance_uid,
        "modality": "CT",
        "description": "PHASE_1",
        "instances": 1,
        "frame_of_reference": ct_series.frame_of_reference_uid,
        "open": True,
    }]


def test_dev_page_names_the_user_for_per_user_drafts(settings, no_toolbar, client, db):
    """#291: drafts in IndexedDB are keyed per user, so the element is told who is logged in."""
    settings.DEBUG = True
    user = get_user_model().objects.create_user(username="draft-user", password="pw")
    client.force_login(user)

    body = client.get(DEV_PAGE, {"series": "2.25.2"}).content.decode()

    assert f'user="{user.pk}"' in body


def test_dev_page_offers_related_series_limited_by_participant_visibility(
    settings, no_toolbar, client, ct_series, tmp_path
):
    """#284/#271: `related` UIDs (repeated or comma-separated) are listed for drag-to-fuse/replace,
    limited by Participant Visibility: unknown and invisible series are left out."""
    settings.DEBUG = True
    elsewhere = ResearchProject.objects.create(name="Not mine", description="#271")
    run_ingestion(elsewhere, write_dicom(build_ct_image(
        patient_id="OTHER-1", patient_name="Other^Patient", study_instance_uid="1.2.9999.43.1.1001",
        series_instance_uid="1.2.9999.43.1.1002", sop_instance_uid="1.2.9999.43.1.1003",
        frame_of_reference_uid="1.2.9999.43.1.1004"), tmp_path / "other.dcm"))
    invisible = DicomSeries.objects.get(study__study_participant__research_project=elsewhere).series_instance_uid
    visible = ct_series.series_instance_uid
    _open_as(client, ct_series, "Annotator")

    query = f"?series={visible}&related={visible},2.25.4&related={invisible}"
    rows = _series_list(client.get(DEV_PAGE + query))

    assert [(row["series"], row["open"]) for row in rows] == [(visible, True)]


def test_dev_page_lists_related_series_after_the_opened_one(settings, no_toolbar, client, ct_series, tmp_path):
    settings.DEBUG = True
    project = ct_series.study.study_participant.research_project
    run_ingestion(project, write_dicom(build_ct_image(
        series_instance_uid="1.2.9999.42.1.2002", sop_instance_uid="1.2.9999.42.1.2003", modality="PT"),
        tmp_path / "pet.dcm"))
    pet = DicomSeries.objects.get(modality="PT").series_instance_uid
    _open_as(client, ct_series, "Annotator")

    rows = _series_list(client.get(DEV_PAGE, {"series": ct_series.series_instance_uid, "related": pet}))

    assert [(row["series"], row["open"]) for row in rows] == [(ct_series.series_instance_uid, True), (pet, False)]


def test_dev_page_with_an_unknown_series_has_an_empty_series_list(settings, no_toolbar, logged_in_client):
    settings.DEBUG = True

    assert _series_list(logged_in_client.get(DEV_PAGE, {"series": "2.25.2"})) == []


def test_dev_page_escapes_query_params(settings, no_toolbar, logged_in_client):
    settings.DEBUG = True

    body = logged_in_client.get(DEV_PAGE, {"series": '"><script>x</script>'}).content.decode()

    assert "<script>x</script>" not in body


def test_base_layout_never_loads_the_viewer_bundle(settings, no_toolbar, logged_in_client):
    settings.DEBUG = False

    body = logged_in_client.get("/monitor/").content.decode()

    assert "mireswc.js" in body  # sanity: this page renders base.html
    assert "mireswc-viewer" not in body


# --- #280 role gating: the page tells the element whether the user may annotate the series. ---

@pytest.fixture
def ct_series(db, settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"
    project = ResearchProject.objects.create(name="Viewer roles", description="#280")
    report = run_ingestion(project, write_dicom(build_ct_image(), tmp_path / "ct.dcm"))
    assert report.counts["ingested"] == 1, report.results
    return DicomSeries.objects.select_related("study__study_participant").get(
        study__study_participant__research_project=project
    )


def _open_as(client, series, role_name) -> str:
    user = get_user_model().objects.create_user(username=f"viewer-{role_name}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(
        user=user, project=series.study.study_participant.research_project, role=role
    )
    client.force_login(user)
    response = client.get(DEV_PAGE, {"series": series.series_instance_uid})
    return response.content.decode()


@pytest.mark.parametrize("role_name", ["Annotator", "PI", "Admin"])
def test_authoring_roles_get_annotate_tools(settings, no_toolbar, client, ct_series, role_name):
    settings.DEBUG = True

    assert "can-annotate" in _open_as(client, ct_series, role_name)


@pytest.mark.parametrize("role_name", ["Investigator", "Contributor"])
def test_view_only_roles_get_no_annotate_tools(settings, no_toolbar, client, ct_series, role_name):
    settings.DEBUG = True

    assert "can-annotate" not in _open_as(client, ct_series, role_name)


def test_unknown_series_gets_no_annotate_tools(settings, no_toolbar, logged_in_client):
    settings.DEBUG = True

    body = logged_in_client.get(DEV_PAGE, {"series": "2.25.2"}).content.decode()

    assert "can-annotate" not in body

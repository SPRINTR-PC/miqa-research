"""WADO for the browser viewer (#276): session callers, Participant Visibility per request, cache headers.

Seam: the WADO HTTP endpoints, fed by `run_ingestion`. A session caller is a
logged-in user (`client.force_login`); a client caller sends a Bearer token.
"""
from datetime import datetime, timezone as dt_timezone
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from contract.constants.audit_log import DATA_ACCESS_EVENT_TYPES, EVENT_TYPE_VIEWER_SERIES_OPENED
from MiqaResearch.data.models import (
    AuditLog,
    Clinic,
    DicomFile,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.data.models.dicom_storage import DicomStorage
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from contract.constants.research_project_role import PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_PI
from tests.client_binding_helpers import bound_client
from tests.dicom_fixtures import build_multiframe_ct, write_dicom

User = get_user_model()
TOKEN = "session-access-test-token"
FRAMES_CACHE_CONTROL = "private, max-age=31536000, immutable"
VIEWER_SESSION = "X-Mires-Viewer-Session"


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def local_media(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def world(db, tmp_path):
    """One ingested multi-frame CT whose participant consented at Site A."""
    project = ResearchProject.objects.create(name="Viewer project", description="Project for #276 tests")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    sites = {code: Clinic.objects.create(clinic_code=f"S-{code}", clinic_name=f"Site {code}") for code in "AB"}
    report = run_ingestion(project, write_dicom(build_multiframe_ct(number_of_frames=3), tmp_path / "ct.dcm"))
    assert report.counts["ingested"] == 1, report.results
    dicom_file = DicomFile.objects.get(sop_instance_uid=report.results[0].sop_instance_uid)
    ParticipantConsent.objects.create(
        study_participant=dicom_file.series.study.study_participant, status="Signerat", clinic=sites["A"],
        consent_type=consent_type, consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    return {"project": project, "sites": sites, "file": dicom_file}


def _user_with_role(project, role_name, clinic=None):
    user = User.objects.create_user(username=f"u-{uuid4().hex[:8]}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role, clinic=clinic)
    return user


@pytest.fixture
def visible_client(client, world):
    client.force_login(_user_with_role(world["project"], PROJECT_ROLE_ANNOTATOR, world["sites"]["A"]))
    return client


@pytest.fixture
def invisible_client(client, world):
    client.force_login(_user_with_role(world["project"], PROJECT_ROLE_ANNOTATOR, world["sites"]["B"]))
    return client


@pytest.fixture
def bearer(world):
    """A client bound to the project, all Sites, granted raw access (#277)."""
    return bound_client(world["project"], dicom_raw=True, scope="read dicom:raw", token=TOKEN)


def _uids(dicom_file):
    return (
        dicom_file.series.study.study_instance_uid, dicom_file.series.series_instance_uid,
        dicom_file.sop_instance_uid,
    )


def _frames_url(dicom_file, frame_list="1"):
    study, series, sop = _uids(dicom_file)
    return f"/api/v1/dicom/studies/{study}/series/{series}/instances/{sop}/frames/{frame_list}"


def _metadata_urls(dicom_file):
    study, series, sop = _uids(dicom_file)
    base = f"/api/v1/dicom/studies/{study}"
    return [
        f"{base}/metadata",
        f"{base}/series/{series}/metadata",
        f"{base}/series/{series}/instances/{sop}/metadata",
    ]


def _raw_urls(dicom_file):
    study, series, sop = _uids(dicom_file)
    base = f"/api/v1/dicom/studies/{study}"
    return [
        f"/api/v1/dicom/wado?requestType=WADO&studyUID={study}&seriesUID={series}&objectUID={sop}",
        base,
        f"{base}/series/{series}",
        f"{base}/series/{series}/instances/{sop}",
    ]


def test_session_caller_who_sees_the_participant_gets_frames(world, visible_client):
    response = visible_client.get(_frames_url(world["file"], "2"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith('multipart/related; type="application/octet-stream"')


def test_session_caller_who_cannot_see_the_participant_gets_404_on_frames(world, invisible_client):
    assert invisible_client.get(_frames_url(world["file"])).status_code == 404


def test_session_caller_gets_series_metadata_only_for_visible_participants(world, visible_client):
    response = visible_client.get(_metadata_urls(world["file"])[1])
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_session_caller_who_cannot_see_the_participant_gets_404_on_metadata(world, invisible_client):
    assert invisible_client.get(_metadata_urls(world["file"])[1]).status_code == 404


@pytest.mark.parametrize("url_index", [0, 2], ids=["study", "instance"])
def test_study_and_instance_metadata_are_403_for_session_callers(world, visible_client, client, bearer, url_index):
    """#271: the viewer surface is series /metadata and /frames only; clients keep the other levels."""
    url = _metadata_urls(world["file"])[url_index]
    assert visible_client.get(url).status_code == 403
    visible_client.logout()
    assert client.get(url, **bearer).status_code == 200


def test_visibility_is_checked_on_every_request(world, client):
    """No memo: losing the role takes effect on the next request."""
    user = _user_with_role(world["project"], PROJECT_ROLE_ANNOTATOR, world["sites"]["A"])
    client.force_login(user)
    assert client.get(_frames_url(world["file"])).status_code == 200

    ResearchProjectUserRoleMap.objects.filter(user=user).delete()

    assert client.get(_frames_url(world["file"])).status_code == 404
    assert client.get(_metadata_urls(world["file"])[1]).status_code == 404


def test_logged_in_user_without_a_role_on_the_project_gets_404(world, client):
    client.force_login(User.objects.create_user(username="norole", password="pw"))

    assert client.get(_frames_url(world["file"])).status_code == 404


def test_project_wide_role_sees_participants_at_every_site(world, client):
    client.force_login(_user_with_role(world["project"], PROJECT_ROLE_PI, world["sites"]["B"]))

    assert client.get(_frames_url(world["file"])).status_code == 200


def _frames_queries(client, url):
    """Queries a /frames request makes, minus the session/user lookups every logged-in request makes."""
    client.get(url)  # warm: frame offset index already stored at ingestion; nothing lazily built
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code in (200, 404)
    return [
        sql for sql in (q["sql"] for q in captured.captured_queries)
        if "django_session" not in sql and not sql.startswith(('SELECT "auth_user"', "SAVEPOINT", "RELEASE SAVEPOINT"))
    ]


@pytest.mark.parametrize("role, site", [(PROJECT_ROLE_ANNOTATOR, "A"), (PROJECT_ROLE_PI, "B"), (PROJECT_ROLE_ANNOTATOR, "B")])
def test_frames_loads_file_and_checks_visibility_in_one_query(world, client, role, site):
    client.force_login(_user_with_role(world["project"], role, world["sites"][site]))

    queries = _frames_queries(client, _frames_url(world["file"], "1,2,3"))

    assert len(queries) == 1, queries
    assert "mires_dicom_file" in queries[0]


def _vary(response):
    return {value.strip().lower() for value in response.get("Vary", "").split(",")}


def test_frames_are_privately_cacheable_forever_with_a_strong_etag(world, visible_client):
    response = visible_client.get(_frames_url(world["file"], "1,2"))

    assert response.status_code == 200
    assert response["Cache-Control"] == FRAMES_CACHE_CONTROL
    assert "accept" in _vary(response)
    etag = response["ETag"]
    assert etag.startswith('"') and etag.endswith('"')  # strong, not W/"..."
    assert visible_client.get(_frames_url(world["file"], "1,2"))["ETag"] == etag
    assert visible_client.get(_frames_url(world["file"], "2,1"))["ETag"] != etag


def test_frames_answer_304_when_the_etag_matches(world, visible_client):
    url = _frames_url(world["file"], "3")
    etag = visible_client.get(url)["ETag"]

    response = visible_client.get(url, HTTP_IF_NONE_MATCH=etag)

    assert response.status_code == 304
    assert response.content == b""
    assert response["ETag"] == etag
    assert response["Cache-Control"] == FRAMES_CACHE_CONTROL


def test_frames_304_still_requires_visibility(world, client):
    user = _user_with_role(world["project"], PROJECT_ROLE_ANNOTATOR, world["sites"]["A"])
    client.force_login(user)
    url = _frames_url(world["file"])
    etag = client.get(url)["ETag"]
    ResearchProjectUserRoleMap.objects.filter(user=user).delete()

    assert client.get(url, HTTP_IF_NONE_MATCH=etag).status_code == 404


def test_metadata_must_be_revalidated_and_answers_304_on_a_matching_etag(world, visible_client):
    url = _metadata_urls(world["file"])[1]
    first = visible_client.get(url)
    assert first.status_code == 200
    assert first["Cache-Control"] == "private, no-cache"
    etag = first["ETag"]

    revalidated = visible_client.get(url, HTTP_IF_NONE_MATCH=etag)
    assert revalidated.status_code == 304
    assert revalidated.content == b""
    assert revalidated["ETag"] == etag
    assert revalidated["Cache-Control"] == "private, no-cache"

    assert visible_client.get(url, HTTP_IF_NONE_MATCH='"stale"').status_code == 200


def test_metadata_reads_only_the_stored_header_when_the_frame_index_is_known(world, visible_client, monkeypatch):
    url = _metadata_urls(world["file"])[1]
    DicomFile.objects.filter(pk=world["file"].pk).update(frame_index=None)
    from_whole_file = visible_client.get(url).json()  # no index yet: whole-file read
    DicomFile.objects.filter(pk=world["file"].pk).update(frame_index=world["file"].frame_index)

    def whole_file_read(*args, **kwargs):
        raise AssertionError("metadata read the whole stored file")

    monkeypatch.setattr(DicomStorage, "_open", whole_file_read)
    response = visible_client.get(url)

    assert response.status_code == 200
    assert response.json() == from_whole_file


def test_raw_endpoints_are_403_for_session_callers(world, visible_client):
    for url in _raw_urls(world["file"]):
        assert visible_client.get(url).status_code == 403, url


def test_raw_endpoints_still_serve_client_callers(world, client, bearer):
    for url in _raw_urls(world["file"]):
        assert client.get(url, **bearer).status_code == 200, url


def test_client_callers_are_not_subject_to_participant_visibility(world, client, bearer):
    """Clients are scoped by their Client Binding (#277, tests/test_wado_client_binding.py), not by a user's."""
    assert client.get(_frames_url(world["file"]), **bearer).status_code == 200
    assert client.get(_metadata_urls(world["file"])[2], **bearer).status_code == 200


def test_anonymous_caller_is_401(world, client):
    assert client.get(_frames_url(world["file"])).status_code == 401


def _series_opens():
    return list(AuditLog.objects.filter(event_type=EVENT_TYPE_VIEWER_SERIES_OPENED))


def test_opening_a_series_in_the_viewer_is_audited_once_per_viewer_open(world, visible_client):
    """#271 story 21: once per open (the series /metadata the viewer opens with), not per frame."""
    open_1, open_2 = {"headers": {VIEWER_SESSION: "open-1"}}, {"headers": {VIEWER_SESSION: "open-2"}}
    series_metadata = _metadata_urls(world["file"])[1]

    assert visible_client.get(series_metadata, **open_1).status_code == 200
    visible_client.get(series_metadata, **open_1)
    for frame in "123":
        visible_client.get(_frames_url(world["file"], frame), **open_1)

    (entry,) = _series_opens()
    assert entry.user_id == int(visible_client.session["_auth_user_id"])
    assert entry.project_id == world["project"].pk
    assert entry.metadata["series_instance_uid"] == world["file"].series.series_instance_uid
    assert entry.event_type in DATA_ACCESS_EVENT_TYPES

    visible_client.get(series_metadata, **open_2)
    assert len(_series_opens()) == 2


def test_denied_series_opens_are_not_audited(world, invisible_client):
    invisible_client.get(_metadata_urls(world["file"])[1], headers={VIEWER_SESSION: "open-1"})
    assert _series_opens() == []


def test_client_callers_write_no_viewer_series_open(world, client, bearer):
    client.get(_metadata_urls(world["file"])[1], **bearer)
    assert _series_opens() == []

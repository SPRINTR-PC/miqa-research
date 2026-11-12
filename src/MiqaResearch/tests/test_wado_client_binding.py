"""WADO for machine clients (#277, ADR 0027): Client Binding, the `dicom:raw` scope, per-token audit.

Seams: the WADO HTTP endpoints (fed by `run_ingestion`) called with a Bearer token, and the OAuth2
token endpoint (`/o/token/`) for which scopes a client may obtain.
"""
from datetime import UTC, datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from oauth2_provider.models import Application

from contract.constants.audit_log import EVENT_TYPE_WADO_CLIENT_ACCESS
from MiqaResearch.data.models import (
    AuditLog,
    ClientBinding,
    Clinic,
    DicomFile,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
)
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.client_binding_helpers import bound_client
from tests.dicom_fixtures import build_multiframe_ct, write_dicom

FRAMES_CACHE_CONTROL = "private, max-age=31536000, immutable"


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
    project = ResearchProject.objects.create(name="Client project", description="Project for #277 tests")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    sites = {code: Clinic.objects.create(clinic_code=f"S-{code}", clinic_name=f"Site {code}") for code in "AB"}
    report = run_ingestion(project, write_dicom(build_multiframe_ct(number_of_frames=3), tmp_path / "ct.dcm"))
    assert report.counts["ingested"] == 1, report.results
    dicom_file = DicomFile.objects.get(sop_instance_uid=report.results[0].sop_instance_uid)
    ParticipantConsent.objects.create(
        study_participant=dicom_file.series.study.participant_key.study_participant, status="Signerat",
        clinic=sites["A"],
        consent_type=consent_type, consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
    )
    return {"project": project, "sites": sites, "file": dicom_file}


def _uids(dicom_file):
    return (
        dicom_file.series.study.study_instance_uid, dicom_file.series.series_instance_uid,
        dicom_file.sop_instance_uid,
    )


def _frames_url(dicom_file, frame_list="1"):
    study, series, sop = _uids(dicom_file)
    return f"/api/v1/dicom/studies/{study}/series/{series}/instances/{sop}/frames/{frame_list}"


def _metadata_url(dicom_file):
    study, series, sop = _uids(dicom_file)
    return f"/api/v1/dicom/studies/{study}/series/{series}/metadata"


def _raw_urls(dicom_file):
    study, series, sop = _uids(dicom_file)
    base = f"/api/v1/dicom/studies/{study}"
    return [
        f"/api/v1/dicom/wado?requestType=WADO&studyUID={study}&seriesUID={series}&objectUID={sop}",
        base,
        f"{base}/series/{series}",
        f"{base}/series/{series}/instances/{sop}",
    ]


def _all_urls(dicom_file):
    return [_frames_url(dicom_file), _metadata_url(dicom_file), *_raw_urls(dicom_file)]


# --- Binding scopes what a client reads ----------------------------------------


def test_unbound_client_gets_404_everywhere(world, client):
    headers = bound_client(world["project"], bound=False, scope="read dicom:raw")

    for url in _all_urls(world["file"]):
        assert client.get(url, **headers).status_code == 404, url


def test_client_bound_to_the_project_without_a_site_reads_frames_and_metadata(world, client):
    headers = bound_client(world["project"])

    assert client.get(_frames_url(world["file"]), **headers).status_code == 200
    assert client.get(_metadata_url(world["file"]), **headers).status_code == 200


def test_client_bound_to_another_project_gets_404(world, client):
    other = ResearchProject.objects.create(name="Other", description="")

    headers = bound_client(other, dicom_raw=True, scope="read dicom:raw")

    for url in _all_urls(world["file"]):
        assert client.get(url, **headers).status_code == 404, url


def test_client_bound_to_a_site_sees_only_that_sites_participants(world, client):
    site_a = bound_client(world["project"], clinic=world["sites"]["A"])
    site_b = bound_client(world["project"], clinic=world["sites"]["B"])

    assert client.get(_frames_url(world["file"]), **site_a).status_code == 200
    assert client.get(_metadata_url(world["file"]), **site_a).status_code == 200
    assert client.get(_frames_url(world["file"]), **site_b).status_code == 404
    assert client.get(_metadata_url(world["file"]), **site_b).status_code == 404


def test_binding_is_checked_on_every_request(world, client):
    headers = bound_client(world["project"])
    assert client.get(_frames_url(world["file"]), **headers).status_code == 200

    ClientBinding.objects.all().delete()

    assert client.get(_frames_url(world["file"]), **headers).status_code == 404


def test_frames_load_the_file_and_check_the_binding_in_one_query(world, client):
    headers = bound_client(world["project"], clinic=world["sites"]["A"])
    url = _frames_url(world["file"], "1,2")
    client.get(url, **headers)

    with CaptureQueriesContext(connection) as captured:
        assert client.get(url, **headers).status_code == 200

    file_queries = [q["sql"] for q in captured.captured_queries if "mires_dicom_file" in q["sql"]]
    assert len(file_queries) == 1, file_queries


def test_client_frames_get_the_same_cache_headers_as_session_callers(world, client):
    headers = bound_client(world["project"])

    response = client.get(_frames_url(world["file"]), **headers)

    assert response["Cache-Control"] == FRAMES_CACHE_CONTROL
    assert client.get(_metadata_url(world["file"]), **headers)["Cache-Control"] == "private, no-cache"


# --- `read` vs `dicom:raw` -----------------------------------------------------


def test_read_alone_is_403_on_raw_endpoints(world, client):
    headers = bound_client(world["project"])

    for url in _raw_urls(world["file"]):
        assert client.get(url, **headers).status_code == 403, url


def test_dicom_raw_grant_and_token_scope_serve_raw_endpoints(world, client):
    headers = bound_client(world["project"], dicom_raw=True, scope="read dicom:raw")

    for url in _raw_urls(world["file"]):
        response = client.get(url, **headers)
        assert response.status_code == 200, url
        assert response["Cache-Control"] == "private, no-store", url


def test_raw_grant_without_the_scope_on_the_token_is_403(world, client):
    headers = bound_client(world["project"], dicom_raw=True, scope="read")

    assert client.get(_raw_urls(world["file"])[3], **headers).status_code == 403


def test_revoking_the_raw_grant_takes_effect_on_tokens_already_issued(world, client):
    headers = bound_client(world["project"], dicom_raw=True, scope="read dicom:raw")
    assert client.get(_raw_urls(world["file"])[3], **headers).status_code == 200

    ClientBinding.objects.update(dicom_raw=False)

    assert client.get(_raw_urls(world["file"])[3], **headers).status_code == 403


def test_raw_endpoints_respect_the_site(world, client):
    headers = bound_client(world["project"], clinic=world["sites"]["B"], dicom_raw=True, scope="read dicom:raw")

    for url in _raw_urls(world["file"]):
        assert client.get(url, **headers).status_code == 404, url


# --- Audit: one entry per client x series x access token ------------------------


def _access_entries():
    return list(AuditLog.objects.filter(event_type=EVENT_TYPE_WADO_CLIENT_ACCESS))


def test_access_is_audited_once_per_client_series_and_token(world, client):
    first_token = bound_client(world["project"], dicom_raw=True, scope="read dicom:raw", token="first")

    client.get(_frames_url(world["file"], "1"), **first_token)
    client.get(_frames_url(world["file"], "2"), **first_token)
    client.get(_metadata_url(world["file"]), **first_token)
    client.get(_raw_urls(world["file"])[2], **first_token)

    (entry,) = _access_entries()
    assert entry.project == world["project"]
    assert entry.user is None
    assert entry.metadata["series_instance_uid"] == world["file"].series.series_instance_uid
    application = ClientBinding.objects.get().application
    assert entry.metadata["client_id"] == application.client_id

    second_token = {"HTTP_AUTHORIZATION": "Bearer second"}
    from oauth2_provider.models import AccessToken
    token = AccessToken.objects.get(token="first")
    AccessToken.objects.create(token="second", application=application, scope="read", expires=token.expires)
    client.get(_frames_url(world["file"]), **second_token)

    assert len(_access_entries()) == 2


def test_denied_requests_write_no_client_access_entry(world, client):
    headers = bound_client(world["project"], clinic=world["sites"]["B"])

    client.get(_frames_url(world["file"]), **headers)

    assert _access_entries() == []


# --- Which scopes a client can obtain ------------------------------------------


def _client_with_secret(project=None, dicom_raw=False):
    application = Application(
        name="token-endpoint", client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS, client_secret="s3cret",
    )
    application.save()
    if project is not None:
        ClientBinding.objects.create(application=application, research_project=project, dicom_raw=dicom_raw)
    return application


def _token(client, application, scope):
    return client.post("/o/token/", {
        "grant_type": "client_credentials", "client_id": application.client_id, "client_secret": "s3cret",
        "scope": scope,
    })


def test_only_a_client_granted_dicom_raw_can_obtain_it(world, client):
    granted = _client_with_secret(world["project"], dicom_raw=True)
    not_granted = _client_with_secret(world["project"])
    unbound = _client_with_secret()

    assert _token(client, granted, "read dicom:raw").status_code == 200
    assert _token(client, not_granted, "read dicom:raw").status_code == 400
    assert _token(client, not_granted, "read").status_code == 200
    assert _token(client, unbound, "read dicom:raw").status_code == 400
    assert _token(client, unbound, "read").status_code == 200

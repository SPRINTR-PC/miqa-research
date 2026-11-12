"""Blinded Annotation and Blinding Reveal (#288, ADR 0026).

Seams: the viewer HTTP API (flag, list, blinding status, reveal, save/retire) under session auth,
WADO /metadata for session callers and bound machine clients, the Data Kind totals, and the Audit Log.
"""
import pytest
from django.test import Client

from contract.constants.audit_log import EVENT_TYPE_BLINDED_ANNOTATION_CHANGED, EVENT_TYPE_BLINDING_REVEAL
from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_ANNOTATOR,
    PROJECT_ROLE_CONTRIBUTOR,
    PROJECT_ROLE_PI,
    PROJECT_ROLE_SITE_PI,
)
from MiqaResearch.data.models import (
    AuditLog,
    Clinic,
    DicomSeries,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.readers.annotation_data_kinds import DATA_KIND_ANNOTATIONS, data_kind_totals
from tests.client_binding_helpers import bound_client
from tests.dicom_derived_fixtures import build_viewer_seg
from tests.dicom_fixtures import build_ct_image
from tests.test_annotations_api import (
    _consent_at,
    _ingest,
    _member,
    _retire,
    _save,
    _seg_for,
    _sr_for,
    _user,
)

OBJECTS_URL = "/api/v1/viewer/objects"
VIEWER_SESSION_HEADER = "X-Mires-Viewer-Session"


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def local_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def client():
    """The viewer's own requests carry its per-open Viewer Session id; a Blinding Reveal is scoped to it."""
    return Client(headers={VIEWER_SESSION_HEADER: "open-1"})


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Blinded", description="#288")


@pytest.fixture
def ct(project, tmp_path):
    return _ingest(project, tmp_path, build_ct_image(), "ct.dcm")


@pytest.fixture
def other_ct(project, tmp_path):
    """A CT of a second participant of the same project."""
    return _ingest(project, tmp_path, build_ct_image(
        patient_id="OTHER-1", patient_name="Other^Patient", study_instance_uid="1.2.9999.43.1.1001",
        series_instance_uid="1.2.9999.43.1.1002", sop_instance_uid="1.2.9999.43.1.1003",
        frame_of_reference_uid="1.2.9999.43.1.1004"), "other.dcm")


def _participant(dicom_file):
    return dicom_file.series.study.participant_key.study_participant


def _blind(project, on=True):
    ResearchProject.objects.filter(pk=project.pk).update(blinded_annotation=on)


def _set_flag(client, user, project, blinded):
    client.force_login(user)
    return client.put(
        f"/api/v1/viewer/projects/{project.pk}/blinded-annotation", {"blinded": blinded},
        content_type="application/json")


def _list_ids(client, user, participant, **params):
    client.force_login(user)
    response = client.get(OBJECTS_URL, {"participant": str(participant.pk), **params})
    assert response.status_code == 200, response.content
    return {item["id"] for item in response.json()}


def _status(client, user, participant):
    client.force_login(user)
    return client.get(f"/api/v1/viewer/participants/{participant.pk}/blinding")


def _reveal(client, user, participant):
    client.force_login(user)
    return client.post(f"/api/v1/viewer/participants/{participant.pk}/blinding-reveal")


def _metadata(client, study_instance_uid, series_instance_uid, **headers):
    return client.get(
        f"/api/v1/dicom/studies/{study_instance_uid}/series/{series_instance_uid}/metadata", **headers)


def _ingested_metadata(client, ingested, **headers):
    return _metadata(client, ingested.series.study.study_instance_uid, ingested.series.series_instance_uid, **headers)


def _ingested_seg(project, tmp_path):
    return _ingest(project, tmp_path, build_viewer_seg(
        referenced_series_uid="1.2.9999.42.1.1002", referenced_sop_uid="1.2.9999.42.1.1003"), "ingested.dcm")


# --- the flag ----------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_PI, PROJECT_ROLE_ADMIN])
def test_pi_and_admin_set_the_flag_and_each_change_is_audited(client, project, role_name):
    user = _member(project, role_name)

    on = _set_flag(client, user, project, True)
    again = _set_flag(client, user, project, True)
    off = _set_flag(client, user, project, False)

    assert (on.status_code, on.json()) == (200, {"blinded": True})
    assert again.status_code == 200
    assert off.json() == {"blinded": False}
    project.refresh_from_db()
    assert project.blinded_annotation is False
    entries = AuditLog.objects.filter(event_type=EVENT_TYPE_BLINDED_ANNOTATION_CHANGED).order_by("logtime")
    assert [(entry.user, entry.project_id, entry.metadata["blinded"]) for entry in entries] == [
        (user, project.pk, True), (user, project.pk, False)]


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_SITE_PI, PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_CONTRIBUTOR])
def test_other_roles_cannot_set_the_flag(client, project, role_name):
    clinic = Clinic.objects.create(clinic_code="A", clinic_name="Site A") if role_name == PROJECT_ROLE_SITE_PI else None

    response = _set_flag(client, _member(project, role_name, clinic=clinic), project, True)

    assert response.status_code == 403
    project.refresh_from_db()
    assert project.blinded_annotation is False


@pytest.mark.django_db
def test_non_members_get_404_on_the_flag(client, project):
    assert _set_flag(client, _user(), project, True).status_code == 404


# --- list, per role, flag on and off -------------------------------------


ALL_ROLES = [
    PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_PI, PROJECT_ROLE_SITE_PI, PROJECT_ROLE_ADMIN, PROJECT_ROLE_CONTRIBUTOR,
]


def _role_member(project, ct, role_name):
    clinic = None
    if role_name == PROJECT_ROLE_SITE_PI:
        clinic = Clinic.objects.create(clinic_code="A", clinic_name="Site A")
        _consent_at(_participant(ct), project, clinic)
    return _member(project, role_name, clinic=clinic)


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ALL_ROLES)
def test_without_the_flag_every_role_sees_everyones_work(client, project, ct, tmp_path, role_name):
    user = _role_member(project, ct, role_name)
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    ingested = _ingested_seg(project, tmp_path)

    ids = _list_ids(client, user, _participant(ct))

    assert others["id"] in ids
    assert str(ingested.series.provenance.pk) in ids


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ALL_ROLES)
def test_with_the_flag_every_role_sees_only_its_own_work(client, project, ct, tmp_path, role_name):
    user = _role_member(project, ct, role_name)
    if role_name == PROJECT_ROLE_CONTRIBUTOR:
        own_ids = set()
    else:
        own_ids = {_save(client, user, _sr_for(ct), [ct.series]).json()["id"]}
    _save(client, _member(project), _sr_for(ct), [ct.series])
    _ingested_seg(project, tmp_path)
    _blind(project)

    assert _list_ids(client, user, _participant(ct)) == own_ids


@pytest.mark.django_db
def test_blinding_hides_others_versions_from_the_history(client, project, ct):
    annotator = _member(project)
    pi = _member(project, PROJECT_ROLE_PI)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    second = _save(client, pi, _sr_for(ct), [ct.series], supersedes=first["id"]).json()
    _blind(project)

    assert _list_ids(client, annotator, _participant(ct)) == set()
    client.force_login(pi)
    (chain,) = client.get(OBJECTS_URL, {"participant": str(_participant(ct).pk)}).json()
    assert chain["id"] == second["id"]
    assert [version["id"] for version in chain["history"]] == [second["id"]]


# --- blinding status ----------------------------------------------------------


@pytest.mark.django_db
def test_status_reports_hidden_chains_and_who_may_reveal(client, project, ct, tmp_path):
    annotator = _member(project)
    pi = _member(project, PROJECT_ROLE_PI)
    _save(client, annotator, _sr_for(ct), [ct.series])
    _save(client, pi, _seg_for(ct), [ct.series])
    _ingested_seg(project, tmp_path)

    assert _status(client, annotator, _participant(ct)).json() == {
        "blinded": False, "revealed": False, "can_reveal": False, "hidden": 0}
    _blind(project)
    assert _status(client, annotator, _participant(ct)).json() == {
        "blinded": True, "revealed": False, "can_reveal": False, "hidden": 2}
    assert _status(client, pi, _participant(ct)).json() == {
        "blinded": True, "revealed": False, "can_reveal": True, "hidden": 2}
    assert _status(client, _user(), _participant(ct)).status_code == 404


# --- Blinding Reveal ------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_PI, PROJECT_ROLE_SITE_PI, PROJECT_ROLE_ADMIN])
def test_reveal_shows_everyones_work_for_one_participant_and_is_audited(
    client, project, ct, other_ct, tmp_path, role_name
):
    user = _role_member(project, ct, role_name)
    if role_name == PROJECT_ROLE_SITE_PI:
        _consent_at(_participant(other_ct), project, Clinic.objects.get(clinic_code="A"))
    annotator = _member(project)
    others = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    others_elsewhere = _save(client, annotator, _sr_for(other_ct), [other_ct.series]).json()
    ingested = _ingested_seg(project, tmp_path)
    _blind(project)

    response = _reveal(client, user, _participant(ct))

    assert response.status_code == 200
    assert response.json()["revealed"] is True
    assert _list_ids(client, user, _participant(ct)) == {others["id"], str(ingested.series.provenance.pk)}
    assert others_elsewhere["id"] not in _list_ids(client, user, _participant(other_ct))
    (entry,) = AuditLog.objects.filter(event_type=EVENT_TYPE_BLINDING_REVEAL)
    assert entry.user == user
    assert entry.project_id == project.pk
    assert entry.metadata["participant_id"] == str(_participant(ct).pk)


@pytest.mark.django_db
def test_reveal_lasts_only_for_this_session(client, project, ct):
    pi = _member(project, PROJECT_ROLE_PI)
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    _blind(project)
    _reveal(client, pi, _participant(ct))
    assert others["id"] in _list_ids(client, pi, _participant(ct))

    another_session = Client()
    assert _list_ids(another_session, pi, _participant(ct)) == set()
    client.logout()
    assert _list_ids(client, pi, _participant(ct)) == set()


@pytest.mark.django_db
def test_reveal_lasts_only_for_this_viewer_open(client, project, ct):
    pi = _member(project, PROJECT_ROLE_PI)
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    _blind(project)
    _reveal(client, pi, _participant(ct))

    client.force_login(pi)
    url = f"/api/v1/viewer/participants/{_participant(ct).pk}/blinding"
    assert client.get(url).json()["revealed"] is True
    assert client.get(url, headers={VIEWER_SESSION_HEADER: "open-2"}).json()["revealed"] is False
    same_login_no_viewer = Client()
    same_login_no_viewer.cookies = client.cookies
    assert same_login_no_viewer.get(url).json()["revealed"] is False
    other_open = Client(headers={VIEWER_SESSION_HEADER: "open-2"})
    other_open.cookies = client.cookies
    assert others["id"] not in _list_ids(other_open, pi, _participant(ct))


@pytest.mark.django_db
def test_reveal_outside_a_viewer_session_is_refused(project, ct):
    _blind(project)
    assert _reveal(Client(), _member(project, PROJECT_ROLE_PI), _participant(ct)).status_code == 400
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_BLINDING_REVEAL).exists()


@pytest.mark.django_db
def test_reveal_ends_when_blinded_annotation_is_turned_off_and_on_again(client, project, ct):
    pi = _member(project, PROJECT_ROLE_PI)
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    _blind(project)
    _reveal(client, pi, _participant(ct))
    assert others["id"] in _list_ids(client, pi, _participant(ct))

    _set_flag(client, pi, project, False)
    _set_flag(client, pi, project, True)

    assert others["id"] not in _list_ids(client, pi, _participant(ct))
    assert _status(client, pi, _participant(ct)).json()["revealed"] is False


@pytest.mark.django_db
def test_annotators_can_never_reveal(client, project, ct):
    annotator = _member(project)
    _save(client, _member(project), _sr_for(ct), [ct.series])
    _blind(project)

    assert _reveal(client, annotator, _participant(ct)).status_code == 403
    assert _list_ids(client, annotator, _participant(ct)) == set()
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_BLINDING_REVEAL).exists()


@pytest.mark.django_db
def test_site_pi_reveals_only_at_its_sites(client, project, ct):
    site_a = Clinic.objects.create(clinic_code="A", clinic_name="Site A")
    site_b = Clinic.objects.create(clinic_code="B", clinic_name="Site B")
    _consent_at(_participant(ct), project, site_a)
    _blind(project)

    assert _reveal(client, _member(project, PROJECT_ROLE_SITE_PI, clinic=site_b), _participant(ct)).status_code == 404


@pytest.mark.django_db
def test_reveal_without_the_flag_is_refused(client, project, ct):
    assert _reveal(client, _member(project, PROJECT_ROLE_PI), _participant(ct)).status_code == 400


@pytest.mark.django_db
def test_reveal_no_longer_counts_once_the_revealer_loses_the_role(client, project, ct):
    pi = _member(project, PROJECT_ROLE_PI)
    _save(client, _member(project), _sr_for(ct), [ct.series])
    _blind(project)
    _reveal(client, pi, _participant(ct))
    ResearchProjectUserRoleMap.objects.filter(user=pi).update(
        role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_ANNOTATOR))

    assert _list_ids(client, pi, _participant(ct)) == set()


# --- changing hidden work ---------------------------------------------------------


@pytest.mark.django_db
def test_hidden_work_cannot_be_superseded_or_retired_until_revealed(client, project, ct):
    pi = _member(project, PROJECT_ROLE_PI)
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    _blind(project)

    assert _save(client, pi, _sr_for(ct), [ct.series], supersedes=others["id"]).status_code == 404
    assert _retire(client, pi, others["id"]).status_code == 404
    _reveal(client, pi, _participant(ct))
    assert _retire(client, pi, others["id"]).status_code == 200


# --- WADO -------------------------------------------------------------------------


@pytest.mark.django_db
def test_session_wado_serves_only_own_work_under_the_flag(client, project, ct, tmp_path):
    pi = _member(project, PROJECT_ROLE_PI)
    own = _save(client, pi, _sr_for(ct), [ct.series]).json()
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    ingested = _ingested_seg(project, tmp_path)
    _blind(project)
    client.force_login(pi)
    study = ct.series.study.study_instance_uid

    assert _metadata(client, study, ct.series.series_instance_uid).status_code == 200
    assert _metadata(client, study, own["series_instance_uid"]).status_code == 200
    assert _metadata(client, study, others["series_instance_uid"]).status_code == 404
    assert _ingested_metadata(client, ingested).status_code == 404

    _reveal(client, pi, _participant(ct))
    assert _metadata(client, study, others["series_instance_uid"]).status_code == 200
    assert _ingested_metadata(client, ingested).status_code == 200


@pytest.mark.django_db
def test_blinding_does_not_apply_to_an_unlinked_study(client, project, ct, tmp_path):
    """ADR 0035 (#415): ingested work on an unlinked Study is shown to who may open it, flag or not."""
    ingested = _ingested_seg(project, tmp_path)
    _blind(project)
    admin = _member(project, PROJECT_ROLE_ADMIN)
    client.force_login(admin)
    assert _ingested_metadata(client, ingested).status_code == 404

    key = ingested.series.study.participant_key
    key.study_participant = None
    key.save(update_fields=["study_participant"])

    assert _ingested_metadata(client, ingested).status_code == 200


@pytest.mark.django_db
def test_session_wado_serves_everyones_work_without_the_flag(client, project, ct):
    others = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    client.force_login(_member(project))
    study = ct.series.study.study_instance_uid

    assert _metadata(client, study, others["series_instance_uid"]).status_code == 200


@pytest.mark.django_db
def test_bound_clients_get_404_on_annotation_and_segmentation_series_under_the_flag(client, project, ct, tmp_path):
    saved = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    ingested = _ingested_seg(project, tmp_path)
    client.logout()
    headers = bound_client(project)
    study = ct.series.study.study_instance_uid

    assert _metadata(client, study, saved["series_instance_uid"], **headers).status_code == 200
    assert _ingested_metadata(client, ingested, **headers).status_code == 200
    _blind(project)
    assert _metadata(client, study, saved["series_instance_uid"], **headers).status_code == 404
    assert _ingested_metadata(client, ingested, **headers).status_code == 404
    assert _metadata(client, study, ct.series.series_instance_uid, **headers).status_code == 200


# --- aggregate counts ---------------------------------------------------------------


@pytest.mark.django_db
def test_aggregate_counts_are_not_filtered(client, project, ct):
    _save(client, _member(project), _sr_for(ct), [ct.series])
    _save(client, _member(project), _sr_for(ct), [ct.series])
    _blind(project)

    series = DicomSeries.objects.filter(study__participant_key__study_participant=_participant(ct))
    assert data_kind_totals(DATA_KIND_ANNOTATIONS, series).count == 2

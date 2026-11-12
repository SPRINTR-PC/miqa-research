"""Participant Key tracking endpoints and Admin actions (#422, ADR 0035).

Seam: the HTTP API under session auth, plus the Audit Log and the key/participant rows.
"""
import json

import pytest
from django.test import Client
from django.urls import reverse

from contract.constants.audit_log import (
    DATA_ACCESS_EVENT_TYPES,
    EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED,
    EVENT_TYPE_PARTICIPANT_KEY_LINKED,
    EVENT_TYPE_PARTICIPANT_KEY_REPOINTED,
    EVENT_TYPE_PARTICIPANT_KEY_UNLINKED,
    EVENT_TYPE_PID_VIEW,
)
from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_ANNOTATOR,
    PROJECT_ROLE_DATA_MANAGER,
)
from MiqaResearch.data.models import (
    AuditLog,
    Clinic,
    ParticipantKey,
    ResearchProject,
    StudyParticipant,
)
from tests.dicom_fixtures import build_ct_image
from tests.test_annotations_api import _consent_at, _ingest, _member, _user


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
def project(db):
    return ResearchProject.objects.create(name="Keys", description="#422")


def _participant(project, alias, psv=None, **kwargs):
    return StudyParticipant.objects.create(alias1=alias, person_source_value=psv, research_project=project, **kwargs)


def _key(project, value="PID-1", participant=None, key_type="dicom:PatientID"):
    return ParticipantKey.objects.create(
        project=project, key_type=key_type, value=value, study_participant=participant)


def _unlinked_study_key(project, tmp_path, **ct_kwargs):
    """A key with one stored Study (original bytes carry DOB 19800101-ish and sex), unlinked."""
    ct = _ingest(project, tmp_path, build_ct_image(**ct_kwargs), "ct.dcm")
    key = ct.series.study.participant_key
    key.study_participant = None
    key.save()
    return key


def _call(user, method, name, **kwargs):
    client = Client()
    client.force_login(user)
    query = kwargs.pop("query", None)
    url = reverse(f"api-v1:{name}", kwargs=kwargs)
    if method == "get":
        return client.get(url, query or {})
    return client.post(url, json.dumps(query or {}), content_type="application/json")


def _table(user, project, **query):
    return _call(user, "get", "participant_key_table", project_id=project.id, query=query)


def _link(user, key, **body):
    return _call(user, "post", "participant_key_link", key_id=key.id, query=body)


def _repoint(user, key, **body):
    return _call(user, "post", "participant_key_repoint", key_id=key.id, query=body)


def _unlink(user, key, **body):
    return _call(user, "post", "participant_key_unlink", key_id=key.id, query=body)


def _admin(project):
    return _member(project, PROJECT_ROLE_ADMIN)


def _manager(project, clinic=None):
    return _member(project, PROJECT_ROLE_DATA_MANAGER, clinic)


# --- table -------------------------------------------------------------------------------------------------

def test_table_lists_keys_masked_with_counts_and_no_audit(project, tmp_path):
    key = _unlinked_study_key(project, tmp_path)
    response = _table(_admin(project), project, include_columns="true")
    assert response.status_code == 200
    (row,) = response.json()["rows"]
    assert row["id"] == str(key.id)
    assert row["key_type"] == "dicom:PatientID"
    assert row["linked"] is False
    assert row["study_count"] == 1
    assert row["series_count"] == 1
    assert "PID" not in json.dumps(response.json()) and key.value not in response.content.decode()
    assert "value" not in row
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW).exists()


def test_table_reveal_needs_reason_and_is_audited_without_values(project):
    _key(project, "SECRET-PID")
    admin = _admin(project)
    assert _table(admin, project, reveal="true").status_code == 400
    assert _table(admin, project, reveal="true", reason="not-a-reason").status_code == 400
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW).exists()

    response = _table(admin, project, reveal="true", reason="data_quality_check")
    assert response.json()["rows"][0]["value"] == "SECRET-PID"
    (entry,) = AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW)
    assert entry.user == admin
    assert entry.project == project
    assert entry.metadata["reason"] == "data_quality_check"
    assert "SECRET-PID" not in json.dumps(entry.metadata)


def test_table_filters_unlinked_only_and_type(project):
    participant = _participant(project, "A1")
    _key(project, "L", participant)
    _key(project, "U")
    _key(project, "U2", key_type="dicom:AccessionNumber")
    admin = _admin(project)
    assert len(_table(admin, project).json()["rows"]) == 3
    assert len(_table(admin, project, linked="false").json()["rows"]) == 2
    both = _table(admin, project, linked="false", key_type="dicom:AccessionNumber").json()["rows"]
    assert [r["key_type"] for r in both] == ["dicom:AccessionNumber"]
    assert _table(admin, project, linked="maybe").status_code == 400
    assert _table(admin, project, value="x").status_code == 400  # not a filter of the masked table


def test_table_scopes_to_the_project_and_participant_visibility(project):
    other = ResearchProject.objects.create(name="Other", description="d")
    _key(other, "OTHER")
    site_a, site_b = Clinic.objects.create(clinic_code="A", clinic_name="A"), Clinic.objects.create(
        clinic_code="B", clinic_name="B")
    at_a, at_b = _participant(project, "PA"), _participant(project, "PB")
    _consent_at(at_a, project, site_a)
    _consent_at(at_b, project, site_b)
    _key(project, "KA", at_a)
    _key(project, "KB", at_b)
    _key(project, "KU")
    manager_a = _manager(project, site_a)
    rows = _table(manager_a, project).json()["rows"]
    assert sorted(r["linked"] for r in rows) == [False, True]
    assert [r["study_participant__alias1"] for r in rows if r["linked"]] == ["PA"]
    assert len(_table(_admin(project), project).json()["rows"]) == 3


@pytest.mark.parametrize("role", [PROJECT_ROLE_ANNOTATOR])
def test_table_refuses_other_roles_and_hides_projects_from_outsiders(project, role):
    assert _table(_member(project, role), project).status_code == 403
    assert _table(_user(), project).status_code == 404
    assert _call(_admin(project), "get", "participant_key_table", project_id="00000000-0000-0000-0000-000000000000"
                 ).status_code == 404


def test_table_allows_data_manager_and_superuser(project):
    _key(project)
    assert _table(_manager(project), project).status_code == 200
    assert _table(_user(is_superuser=True), project).status_code == 200


# --- participant search ------------------------------------------------------------------------------------

def _search(user, project, q):
    return _call(user, "get", "participant_key_participant_search", project_id=project.id, query={"q": q})


def test_participant_search_by_alias_returns_no_identity(project):
    _participant(project, "ALPHA-1", psv="199001011234", name="Real Name")
    _participant(project, "BETA-1")
    hits = _search(_manager(project), project, "alph").json()
    assert hits == [{"id": str(StudyParticipant.objects.get(alias1="ALPHA-1").id), "alias": "ALPHA-1"}]
    assert _search(_member(project, PROJECT_ROLE_ANNOTATOR), project, "a").status_code == 403


# --- link --------------------------------------------------------------------------------------------------

def test_link_by_participant_id_audits_with_ids_only(project):
    key, participant = _key(project, "SECRET"), _participant(project, "A1")
    manager = _manager(project)
    response = _link(manager, key, participant_id=str(participant.id))
    assert response.status_code == 200
    assert response.json()["linked"] is True
    key.refresh_from_db()
    assert key.study_participant == participant
    assert key.linked_via == "admin"
    assert key.linked_at is not None
    (entry,) = AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_LINKED)
    assert entry.user == manager
    assert entry.project == project
    assert entry.metadata == {"key_id": str(key.id), "participant_id": str(participant.id), "fill_demographics": False}
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW).exists()


def test_link_by_exact_pid_is_an_audited_identity_reveal(project):
    key, participant = _key(project), _participant(project, "A1", psv="199001011234")
    admin = _admin(project)
    assert _link(admin, key, person_source_value="19900101-1234").status_code == 400  # no reason
    assert _link(admin, key, person_source_value="19900101-1234", reveal_reason="bogus").status_code == 400
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW).exists()

    response = _link(admin, key, person_source_value="19900101-1234", reveal_reason="link_participant_key")
    assert response.status_code == 200
    key.refresh_from_db()
    assert key.study_participant == participant
    (reveal,) = AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW)
    assert reveal.metadata["reason"] == "link_participant_key"
    assert "199001011234" not in json.dumps(reveal.metadata)


def test_unknown_pid_is_rejected_but_still_audited(project):
    key = _key(project)
    response = _link(_admin(project), key, person_source_value="nope", reveal_reason="link_participant_key")
    assert response.status_code == 400
    key.refresh_from_db()
    assert key.study_participant is None
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW).count() == 1
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_LINKED).exists()


def test_link_rejects_unknown_other_project_and_invisible_participants_and_bad_shapes(project):
    key = _key(project)
    other = ResearchProject.objects.create(name="Other", description="d")
    foreign = _participant(other, "F1")
    site = Clinic.objects.create(clinic_code="A", clinic_name="A")
    elsewhere = _participant(project, "NOT-MINE")
    _consent_at(elsewhere, project, Clinic.objects.create(clinic_code="B", clinic_name="B"))
    manager = _manager(project, site)
    admin = _admin(project)
    unknown = "00000000-0000-0000-0000-000000000000"
    assert _link(admin, key, participant_id=unknown).status_code == 400
    assert _link(admin, key, participant_id=str(foreign.id)).status_code == 400
    assert _link(manager, key, participant_id=str(elsewhere.id)).status_code == 400  # outside visibility
    assert _link(admin, key).status_code == 400  # neither
    assert _link(admin, key, participant_id=str(elsewhere.id), person_source_value="x").status_code == 400  # both
    key.refresh_from_db()
    assert key.study_participant is None


def test_link_role_matrix_and_unknown_key(project):
    key, participant = _key(project), _participant(project, "A1")
    body = {"participant_id": str(participant.id)}
    assert _link(_member(project, PROJECT_ROLE_ANNOTATOR), key, **body).status_code == 403
    assert _link(_user(), key, **body).status_code == 404
    other = ResearchProject.objects.create(name="Other", description="d")
    assert _link(_admin(other), key, **body).status_code == 404  # key of a project the caller has no role on
    ghost = _call(_admin(project), "post", "participant_key_link", key_id="00000000-0000-0000-0000-000000000000",
                  query=body)
    assert ghost.status_code == 404
    assert _link(_user(is_superuser=True), key, **body).status_code == 200


def test_link_is_idempotent_for_same_participant_and_refuses_another(project):
    participant, other = _participant(project, "A1"), _participant(project, "A2")
    key = _key(project, participant=participant)
    admin = _admin(project)
    again = _link(admin, key, participant_id=str(participant.id))
    assert again.status_code == 200
    assert again.json()["changed"] is False
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_LINKED).exists()
    assert _link(admin, key, participant_id=str(other.id)).status_code == 400
    key.refresh_from_db()
    assert key.study_participant == participant


def test_link_fills_blank_demographics_only_and_audits_without_values(project, tmp_path):
    key = _unlinked_study_key(project, tmp_path, patient_birth_date="19800214", patient_sex="F")
    participant = _participant(project, "A1")  # blank DOB, sex U
    response = _link(_admin(project), key, participant_id=str(participant.id), fill_demographics=True)
    assert response.status_code == 200
    assert sorted(response.json()["demographics_filled"]) == ["date_of_birth", "sex"]
    participant.refresh_from_db()
    assert (participant.year_of_birth, participant.month_of_birth, participant.day_of_birth) == (1980, 2, 14)
    assert participant.gender == "F"
    (entry,) = AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED)
    assert entry.metadata["fields"] == ["date_of_birth", "sex"]
    assert "1980" not in json.dumps(entry.metadata)


def test_link_never_overwrites_demographics_and_reports_mismatch(project, tmp_path):
    key = _unlinked_study_key(project, tmp_path, patient_birth_date="19800214", patient_sex="F")
    participant = _participant(project, "A1", year_of_birth=1999, month_of_birth=1, day_of_birth=1, gender="M")
    response = _link(_admin(project), key, participant_id=str(participant.id), fill_demographics=True)
    assert response.status_code == 200
    assert response.json()["demographics_filled"] == []
    assert sorted(response.json()["demographics_mismatched"]) == ["date_of_birth", "sex"]
    participant.refresh_from_db()
    assert (participant.year_of_birth, participant.gender) == (1999, "M")
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED).exists()


@pytest.mark.parametrize(("birth", "expected"), [
    ("1975", (1975, None, None)),
    ("197500", (1975, None, None)),
    ("19750000", (1975, None, None)),
    ("197503", (1975, 3, None)),
    ("19750300", (1975, 3, None)),
    ("19751300", (1975, None, None)),  # month out of range: kept as year only
    ("17990101", (None, None, None)),  # implausible year
    ("abcd0101", (None, None, None)),
    ("", (None, None, None)),
])
def test_link_fills_partial_and_rejects_invalid_birth_dates_like_the_datatype(project, tmp_path, birth, expected):
    """Admin Link shares the one demographics implementation with the participant_key_link Datatype."""
    key = _unlinked_study_key(project, tmp_path, patient_birth_date=birth, patient_sex="O")
    participant = _participant(project, "A1")
    response = _link(_admin(project), key, participant_id=str(participant.id), fill_demographics=True)
    assert response.status_code == 200
    participant.refresh_from_db()
    assert (participant.year_of_birth, participant.month_of_birth, participant.day_of_birth) == expected
    assert participant.gender == "O"  # DICOM sex "O" maps like in the Datatype
    assert ("date_of_birth" in response.json()["demographics_filled"]) == (expected[0] is not None)


def test_the_actions_guard_the_reason_even_without_the_api_schema(project):
    from MiqaResearch.actions.participant_key_admin import InvalidKeyAction, unlink_key

    admin = _admin(project)
    key = _key(project, "K", participant=_participant(project, "A1"))
    for reason in ("", "  ", "x" * 501):
        with pytest.raises(InvalidKeyAction):
            unlink_key(user=admin, key_id=key.id, reason=reason)


def test_link_without_the_checkbox_leaves_demographics(project, tmp_path):
    key = _unlinked_study_key(project, tmp_path)
    participant = _participant(project, "A1")
    _link(_admin(project), key, participant_id=str(participant.id))
    participant.refresh_from_db()
    assert participant.year_of_birth is None
    assert participant.gender == "U"


# --- re-point and unlink -----------------------------------------------------------------------------------

def test_repoint_moves_key_and_studies_and_audits_old_and_new(project, tmp_path):
    ct = _ingest(project, tmp_path, build_ct_image(), "ct.dcm")
    key = ct.series.study.participant_key
    old = key.study_participant
    new = _participant(project, "NEW-1")
    admin = _admin(project)
    response = _repoint(admin, key, participant_id=str(new.id), reason="Wrong participant")
    assert response.status_code == 200
    key.refresh_from_db()
    assert key.study_participant == new
    ct.series.study.refresh_from_db()
    assert ct.series.study.participant_key.study_participant == new
    (entry,) = AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_REPOINTED)
    assert entry.user == admin
    assert entry.project == project
    assert entry.metadata == {
        "key_id": str(key.id), "old_participant_id": str(old.id), "new_participant_id": str(new.id),
        "reason": "Wrong participant"}


def test_repoint_and_unlink_are_admin_only_with_a_reason(project):
    old, new = _participant(project, "A1"), _participant(project, "A2")
    key = _key(project, participant=old)
    manager = _manager(project)
    assert _repoint(manager, key, participant_id=str(new.id), reason="why").status_code == 403
    assert _unlink(manager, key, reason="why").status_code == 403
    assert _repoint(_user(), key, participant_id=str(new.id), reason="why").status_code == 404
    admin = _admin(project)
    assert _repoint(admin, key, participant_id=str(new.id), reason="  ").status_code == 422
    assert _repoint(admin, key, participant_id=str(new.id), reason="x" * 501).status_code == 422
    assert _unlink(admin, key, reason="").status_code == 422
    assert _call(admin, "post", "participant_key_unlink", key_id=key.id).status_code == 422  # reason missing
    key.refresh_from_db()
    assert key.study_participant == old
    assert not AuditLog.objects.filter(event_type__in=[
        EVENT_TYPE_PARTICIPANT_KEY_REPOINTED, EVENT_TYPE_PARTICIPANT_KEY_UNLINKED]).exists()


def test_repoint_needs_linked_key_and_a_different_known_participant(project):
    old, new = _participant(project, "A1"), _participant(project, "A2")
    admin = _admin(project)
    assert _repoint(admin, _key(project, "U"), participant_id=str(new.id), reason="r").status_code == 400
    key = _key(project, "L", old)
    assert _repoint(admin, key, participant_id=str(old.id), reason="r").status_code == 400
    assert _repoint(admin, key, participant_id="00000000-0000-0000-0000-000000000000", reason="r").status_code == 400
    key.refresh_from_db()
    assert key.study_participant == old


def test_repoint_by_exact_pid_is_an_identity_reveal(project):
    old, new = _participant(project, "A1"), _participant(project, "A2", psv="199001011234")
    key = _key(project, participant=old)
    response = _repoint(
        _admin(project), key, person_source_value="199001011234", reveal_reason="link_participant_key", reason="fix")
    assert response.status_code == 200
    key.refresh_from_db()
    assert key.study_participant == new
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_PID_VIEW).count() == 1


def test_unlink_returns_studies_to_unlinked_state_and_audits_old_participant(project, tmp_path):
    ct = _ingest(project, tmp_path, build_ct_image(), "ct.dcm")
    key = ct.series.study.participant_key
    old = key.study_participant
    admin = _admin(project)
    response = _unlink(admin, key, reason="Linked in error")
    assert response.status_code == 200
    assert response.json()["linked"] is False
    key.refresh_from_db()
    assert key.study_participant is None
    assert (key.linked_via, key.linked_job, key.linked_at) == ("", None, None)
    assert ct.series.study.__class__.objects.get(pk=ct.series.study_id).participant_key.study_participant is None
    (entry,) = AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_UNLINKED)
    assert entry.metadata == {"key_id": str(key.id), "old_participant_id": str(old.id), "reason": "Linked in error"}
    assert _unlink(admin, key, reason="again").status_code == 400  # already unlinked


def test_new_events_are_data_access_events():
    assert {
        EVENT_TYPE_PARTICIPANT_KEY_LINKED, EVENT_TYPE_PARTICIPANT_KEY_REPOINTED,
        EVENT_TYPE_PARTICIPANT_KEY_UNLINKED, EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED,
    } <= DATA_ACCESS_EVENT_TYPES

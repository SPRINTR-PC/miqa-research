"""Viewer page (#279) on the entry contract decided in #184.

Seam: the HTTP response of `/projects/<project>/participants/<participant>/viewer/?series=…`
(status, the JSON series list, the element's attributes), the Audit Log, and `viewer_url`, which builds
the page URL for "Open" links.
"""
import json
import re
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from contract.constants.audit_log import DATA_ACCESS_EVENT_TYPES, EVENT_TYPE_VIEWER_OPEN
from contract.constants.research_project_role import PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_INVESTIGATOR
from MiqaResearch.data.models import (
    AuditLog,
    Clinic,
    DicomSeries,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.interfaces.http.views.viewer.page import viewer_url
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_derived_fixtures import build_viewer_sr
from tests.dicom_fixtures import build_ct_image, write_dicom

User = get_user_model()


@pytest.fixture(autouse=True)
def environment(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Viewer page", description="#279")


def _ingest(project, tmp_path, name, **tags) -> DicomSeries:
    report = run_ingestion(project, write_dicom(build_ct_image(**tags), tmp_path / f"{name}.dcm"))
    assert report.counts["ingested"] == 1, report.results
    return DicomSeries.objects.select_related("study__study_participant").get(
        dicomfile__sop_instance_uid=report.results[0].sop_instance_uid
    )


@pytest.fixture
def ct(project, tmp_path) -> DicomSeries:
    return _ingest(project, tmp_path, "ct")


def _member(client, project, role_name=PROJECT_ROLE_ANNOTATOR, clinic=None):
    user = User.objects.create_user(username=f"u-{uuid4().hex[:8]}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role, clinic=clinic)
    client.force_login(user)
    return user


def _open(client, series: DicomSeries, *uids: str, project_id=None, participant_id=None):
    participant = series.study.study_participant
    project_id = project_id or participant.research_project_id
    url = f"/projects/{project_id}/participants/{participant_id or participant.pk}/viewer/"
    return client.get(url, {"series": list(uids) or [series.series_instance_uid]})


def _series_list(response) -> list[dict]:
    pattern = r'<script id="viewer-series" type="application/json">(.*?)</script>'
    match = re.search(pattern, response.content.decode(), re.S)
    assert match, "no series list on the page"
    return json.loads(match.group(1))


def test_page_lists_the_opened_series_for_the_viewer(client, project, ct):
    _member(client, project)

    response = _open(client, ct)

    assert response.status_code == 200
    assert _series_list(response) == [{
        "study": ct.study.study_instance_uid,
        "series": ct.series_instance_uid,
        "modality": "CT",
        "description": "PHASE_1",
        "instances": 1,
        "frame_of_reference": ct.frame_of_reference_uid,
        "open": True,
    }]


def test_opened_series_come_first_in_request_order_then_related_series_from_every_study(client, project, ct, tmp_path):
    pet = _ingest(project, tmp_path, "pet", series_instance_uid="1.2.9999.42.1.2002",
                  sop_instance_uid="1.2.9999.42.1.2003",
                  modality="PT", series_description="PET AC")
    follow_up = _ingest(project, tmp_path, "followup", study_instance_uid="1.2.9999.42.2.1001",
                        series_instance_uid="1.2.9999.42.2.1002", sop_instance_uid="1.2.9999.42.2.1003",
                        study_date="20250101")
    _member(client, project)

    rows = _series_list(_open(client, ct, pet.series_instance_uid, ct.series_instance_uid))

    assert [(r["series"], r["open"]) for r in rows] == [
        (pet.series_instance_uid, True),
        (ct.series_instance_uid, True),
        (follow_up.series_instance_uid, False),
    ]
    assert rows[2]["study"] == follow_up.study.study_instance_uid != ct.study.study_instance_uid


def test_anonymous_user_is_sent_to_login(client, ct):
    response = _open(client, ct)

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_user_without_a_role_on_the_project_gets_404(client, ct):
    _member(client, ResearchProject.objects.create(name="Elsewhere", description="#279"))

    assert _open(client, ct).status_code == 404


def test_participant_of_another_project_gets_404(client, project, ct):
    _member(client, project)
    other = ResearchProject.objects.create(name="Other", description="#279")

    assert _open(client, ct, project_id=other.pk).status_code == 404


def test_a_series_of_another_participant_makes_the_whole_page_404(client, project, ct, tmp_path):
    someone_else = _ingest(project, tmp_path, "else", patient_id="OTHER-1", patient_name="Other^Patient",
                           study_instance_uid="1.2.9999.43.1.1001", series_instance_uid="1.2.9999.43.1.1002",
                           sop_instance_uid="1.2.9999.43.1.1003")
    _member(client, project)

    assert _open(client, ct, ct.series_instance_uid, someone_else.series_instance_uid).status_code == 404


def test_unknown_series_or_no_series_is_404(client, project, ct):
    _member(client, project)
    participant = ct.study.study_participant

    assert _open(client, ct, "2.25.404").status_code == 404
    assert client.get(f"/projects/{project.pk}/participants/{participant.pk}/viewer/").status_code == 404


def test_participant_outside_the_users_sites_gets_404(client, project, ct):
    """No consent at the user's Site: outside Participant Visibility."""
    _member(client, project, clinic=Clinic.objects.create(clinic_code="A", clinic_name="Site A"))

    assert _open(client, ct).status_code == 404


def _ingested_sr(project, tmp_path) -> DicomSeries:
    raw = build_viewer_sr(referenced_study_uid="1.2.9999.42.1.1001", referenced_series_uid="1.2.9999.42.1.1002",
                          referenced_sop_uid="1.2.9999.42.1.1003")
    report = run_ingestion(project, write_dicom(raw, tmp_path / "sr.dcm"))
    assert report.counts["ingested"] == 1, report.results
    return DicomSeries.objects.get(dicomfile__sop_instance_uid=report.results[0].sop_instance_uid)


def test_annotation_and_segmentation_series_are_not_offered_and_cannot_be_opened(client, project, ct, tmp_path):
    """They are results (shown by the results tree), not images to fuse or show instead."""
    sr = _ingested_sr(project, tmp_path)
    _member(client, project)

    assert [r["series"] for r in _series_list(_open(client, ct))] == [ct.series_instance_uid]
    assert _open(client, ct, sr.series_instance_uid).status_code == 404


def test_page_hosts_the_viewer_named_by_alias_only(client, project, ct):
    user = _member(client, project)
    participant = ct.study.study_participant

    response = _open(client, ct)

    body = response.content.decode()
    assert f"<title>{participant.alias1}</title>" in body
    assert "js/viewer/mireswc-viewer.js" in body
    assert f'participant="{participant.pk}"' in body
    assert f'user="{user.pk}"' in body
    assert 'series-list="viewer-series"' in body
    assert "csrftoken" in response.cookies


@pytest.mark.parametrize(
    ("role_name", "annotates"), [(PROJECT_ROLE_ANNOTATOR, True), (PROJECT_ROLE_INVESTIGATOR, False)]
)
def test_annotate_tools_follow_the_users_rights(client, project, ct, role_name, annotates):
    _member(client, project, role_name)

    assert ("can-annotate" in _open(client, ct).content.decode()) is annotates


def test_each_page_load_is_one_viewer_open_audit_entry(client, project, ct, tmp_path):
    pet = _ingest(project, tmp_path, "pet", series_instance_uid="1.2.9999.42.1.2002",
                  sop_instance_uid="1.2.9999.42.1.2003",
                  modality="PT")
    user = _member(client, project)

    first = _open(client, ct, ct.series_instance_uid, pet.series_instance_uid)
    _open(client, ct)

    entries = list(AuditLog.objects.filter(event_type=EVENT_TYPE_VIEWER_OPEN).order_by("logtime"))
    assert len(entries) == 2
    entry = entries[0]
    assert entry.user == user
    assert entry.project_id == project.pk
    assert entry.metadata["series_uids"] == [ct.series_instance_uid, pet.series_instance_uid]
    assert entry.metadata["participant_ids"] == [str(ct.study.study_participant.pk)]
    assert entry.metadata["fused"] is True
    assert entries[1].metadata["fused"] is False
    # the entry names the page's Viewer Session, which the element sends with its requests
    assert f'viewer-session="{entry.metadata["viewer_session"]}"' in first.content.decode()
    assert entry.metadata["viewer_session"] != entries[1].metadata["viewer_session"]
    assert EVENT_TYPE_VIEWER_OPEN in DATA_ACCESS_EVENT_TYPES


def test_a_refused_open_is_not_audited(client, project, ct):
    _member(client, project)

    _open(client, ct, "2.25.404")

    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_VIEWER_OPEN).exists()


def test_related_series_are_only_the_participants_own(client, project, ct, tmp_path):
    someone_else = _ingest(project, tmp_path, "else", patient_id="OTHER-1", patient_name="Other^Patient",
                           study_instance_uid="1.2.9999.43.1.1001", series_instance_uid="1.2.9999.43.1.1002",
                           sop_instance_uid="1.2.9999.43.1.1003")
    _member(client, project)

    listed = [r["series"] for r in _series_list(_open(client, ct))]

    assert someone_else.series_instance_uid not in listed


def test_viewer_url_opens_the_series_in_order(client, project, ct, tmp_path):
    pet = _ingest(project, tmp_path, "pet", series_instance_uid="1.2.9999.42.1.2002",
                  sop_instance_uid="1.2.9999.42.1.2003", modality="PT")
    _member(client, project)
    participant = ct.study.study_participant

    url = viewer_url(project.pk, participant.pk, [pet.series_instance_uid, ct.series_instance_uid])

    rows = _series_list(client.get(url))
    assert [(r["series"], r["open"]) for r in rows] == [(pet.series_instance_uid, True), (ct.series_instance_uid, True)]

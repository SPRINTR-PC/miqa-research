"""Annotations and Segmentations backend (#287): save, supersede, 409, retire, list.

Seams: the HTTP API under /api/v1/viewer/objects (session auth), the stored
object as WADO would read it (the stored file bytes), `run_ingestion` for
ingested SR/SEG, the Data Kind classifier, and the Audit Log.
"""
import io
from datetime import UTC, datetime
from uuid import uuid4

import pydicom
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

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
    DicomFile,
    DicomSeries,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.readers.annotation_data_kinds import (
    DATA_KIND_ANNOTATIONS,
    DATA_KIND_DICOM_SERIES,
    DATA_KIND_SEGMENTATIONS,
    data_kind_for_modality,
    data_kind_totals,
)
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_derived_fixtures import build_viewer_seg, build_viewer_sr
from tests.dicom_fixtures import build_ct_image, write_dicom

OBJECTS_URL = "/api/v1/viewer/objects"
User = get_user_model()


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
def project(db):
    return ResearchProject.objects.create(name="Annotations", description="#287")


@pytest.fixture
def ct(project, tmp_path) -> DicomFile:
    """An ingested CT image: its DB UIDs are the pseudonyms the viewer sees."""
    return _ingest(project, tmp_path, build_ct_image(), "ct.dcm")


def _ingest(project, tmp_path, ds, name) -> DicomFile:
    report = run_ingestion(project, write_dicom(ds, tmp_path / name))
    assert report.counts["ingested"] == 1, report.results
    return DicomFile.objects.select_related("series__study__study_participant").get(
        sop_instance_uid=report.results[0].sop_instance_uid
    )


def _user(**kwargs):
    return User.objects.create_user(username=f"u-{uuid4().hex[:8]}", password="pw", **kwargs)


def _grant(user, project, role_name, clinic=None):
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role, clinic=clinic)
    return user


def _member(project, role_name=PROJECT_ROLE_ANNOTATOR, clinic=None):
    return _grant(_user(), project, role_name, clinic)


def _consent_at(participant, project, clinic):
    consent_type, _ = ParticipantConsentType.objects.get_or_create(label="Participation", research_project=project)
    ParticipantConsent.objects.create(
        study_participant=participant, status="Signerat", clinic=clinic, consent_type=consent_type,
        consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
    )


def _sr_for(ct: DicomFile, **kwargs):
    return build_viewer_sr(
        referenced_study_uid=ct.series.study.study_instance_uid,
        referenced_series_uid=ct.series.series_instance_uid,
        referenced_sop_uid=ct.sop_instance_uid,
        frame_of_reference_uid=ct.frame_of_reference_uid,
        **kwargs,
    )


def _seg_for(ct: DicomFile, **kwargs):
    return build_viewer_seg(
        referenced_series_uid=ct.series.series_instance_uid,
        referenced_sop_uid=ct.sop_instance_uid,
        frame_of_reference_uid=ct.frame_of_reference_uid,
        **kwargs,
    )


def _upload(ds) -> SimpleUploadedFile:
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return SimpleUploadedFile("object.dcm", buffer.getvalue(), content_type="application/dicom")


def _save(client, user, ds, source_series, supersedes=None):
    client.force_login(user)
    data = {"file": _upload(ds), "source_series": [series.series_instance_uid for series in source_series]}
    if supersedes is not None:
        data["supersedes"] = str(supersedes)
    return client.post(OBJECTS_URL, data)


def _stored(series_instance_uid: str):
    dcm_file = DicomFile.objects.get(series__series_instance_uid=series_instance_uid)
    with dcm_file.file.storage.open(dcm_file.file.name, "rb") as stored:
        return pydicom.dcmread(stored)


# --- save round trip -------------------------------------------------------


@pytest.mark.django_db
def test_saved_sr_is_sanitized_with_server_uids_and_keeps_its_references(client, project, ct):
    annotator = _member(project)

    response = _save(client, annotator, _sr_for(ct), [ct.series])

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["kind"] == "annotation"
    assert body["version"] == 1
    assert body["author"] == annotator.username
    assert body["source_series_uids"] == [ct.series.series_instance_uid]
    stored = _stored(body["series_instance_uid"])
    participant = ct.series.study.study_participant
    # patient/study from the DB, never from the browser
    assert str(stored.PatientName) == participant.alias1
    assert stored.PatientID == participant.alias1
    assert stored.StudyInstanceUID == ct.series.study.study_instance_uid
    assert stored.SeriesInstanceUID == body["series_instance_uid"] != "2.25.2222"
    assert stored.SOPInstanceUID != "2.25.3333"
    assert stored.file_meta.MediaStorageSOPInstanceUID == stored.SOPInstanceUID
    # profile applied
    assert "OtherPatientIDs" not in stored
    assert "PatientAddress" not in stored
    assert stored.PatientIdentityRemoved == "YES"
    # references were already pseudonyms: kept as they are, never hashed again
    evidence = stored.CurrentRequestedProcedureEvidenceSequence[0]
    assert evidence.StudyInstanceUID == ct.series.study.study_instance_uid
    assert evidence.ReferencedSeriesSequence[0].SeriesInstanceUID == ct.series.series_instance_uid
    assert stored.ContentSequence[1].ReferencedSOPSequence[0].ReferencedSOPInstanceUID == ct.sop_instance_uid
    assert stored.FrameOfReferenceUID == ct.frame_of_reference_uid
    # an ordinary Dicom Series in the source Dicom Study
    series = DicomSeries.objects.get(series_instance_uid=body["series_instance_uid"])
    assert series.study_id == ct.series.study_id
    assert series.modality == "SR"


@pytest.mark.django_db
def test_saved_seg_is_a_segmentation_whose_metadata_dump_keeps_pseudonymized_references(client, project, ct):
    response = _save(client, _member(project), _seg_for(ct), [ct.series])

    assert response.status_code == 201, response.content
    assert response.json()["kind"] == "segmentation"
    dcm_file = DicomFile.objects.get(series__series_instance_uid=response.json()["series_instance_uid"])
    assert dcm_file.uids_pseudonymized is True
    assert dcm_file.metadata["ReferencedSeriesSequence"][0]["SeriesInstanceUID"] == ct.series.series_instance_uid
    assert dcm_file.metadata["PatientID"] == ct.series.study.study_participant.alias1


@pytest.mark.django_db
def test_save_is_audited_as_a_create_event(client, project, ct):
    annotator = _member(project)

    body = _save(client, annotator, _sr_for(ct), [ct.series]).json()

    entry = AuditLog.objects.get(event_type="annotation_created")
    assert entry.user == annotator
    assert entry.project == project
    assert entry.metadata["series_instance_uid"] == body["series_instance_uid"]
    assert entry.metadata["version"] == 1


@pytest.mark.django_db
def test_upload_that_is_not_sr_or_seg_is_rejected(client, project, ct):
    response = _save(client, _member(project), build_ct_image(), [ct.series])

    assert response.status_code == 400


@pytest.mark.django_db
def test_source_series_with_different_frames_of_reference_are_rejected(client, project, ct, tmp_path):
    other = _ingest(project, tmp_path, build_ct_image(
        series_instance_uid="1.2.9999.42.1.2002", sop_instance_uid="1.2.9999.42.1.2003",
        frame_of_reference_uid="1.2.9999.42.1.2004",
    ), "other.dcm")

    response = _save(client, _member(project), _sr_for(ct), [ct.series, other.series])

    assert response.status_code == 400
    assert "Frame of Reference" in response.json()["detail"]


@pytest.mark.django_db
def test_save_needs_a_session(client, ct):
    data = {"file": _upload(_sr_for(ct)), "source_series": [ct.series.series_instance_uid]}

    response = client.post(OBJECTS_URL, data)

    assert response.status_code == 401


@pytest.mark.django_db
def test_save_without_csrf_token_is_refused(project, ct):
    from django.test import Client

    csrf_client = Client(enforce_csrf_checks=True)

    response = _save(csrf_client, _member(project), _sr_for(ct), [ct.series])

    assert response.status_code == 403
    assert not DicomSeries.objects.filter(modality="SR").exists()


# --- supersede and 409 -----------------------------------------------------


@pytest.mark.django_db
def test_supersede_makes_the_next_version_of_the_chain(client, project, ct):
    annotator = _member(project)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()

    response = _save(client, annotator, _sr_for(ct), [ct.series], supersedes=first["id"])

    assert response.status_code == 201, response.content
    second = response.json()
    assert second["version"] == 2
    assert second["chain_id"] == first["chain_id"]
    assert second["series_instance_uid"] != first["series_instance_uid"]
    entry = AuditLog.objects.get(event_type="annotation_superseded")
    assert entry.metadata["predecessor_series_instance_uid"] == first["series_instance_uid"]


@pytest.mark.django_db
def test_superseding_a_stale_head_is_409_with_the_current_head(client, project, ct):
    annotator = _member(project)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    second = _save(client, annotator, _sr_for(ct), [ct.series], supersedes=first["id"]).json()

    response = _save(client, annotator, _sr_for(ct), [ct.series], supersedes=first["id"])

    assert response.status_code == 409
    assert response.json()["head"]["id"] == second["id"]
    assert response.json()["head"]["version"] == 2
    assert DicomSeries.objects.filter(modality="SR").count() == 2


@pytest.mark.django_db
def test_the_409_says_whether_the_caller_may_save_on_top_of_the_newer_head(client, project, ct):
    """The viewer's 409 dialog offers "Save mine on top" only when the caller may change the head (#289)."""
    author, other, pi = _member(project), _member(project), _member(project, PROJECT_ROLE_PI)
    first = _save(client, author, _sr_for(ct), [ct.series]).json()
    _save(client, author, _sr_for(ct), [ct.series], supersedes=first["id"])

    assert _save(client, author, _sr_for(ct), [ct.series], supersedes=first["id"]).json()["can_change"] is True
    assert _save(client, pi, _sr_for(ct), [ct.series], supersedes=first["id"]).json()["can_change"] is True
    assert _save(client, other, _sr_for(ct), [ct.series], supersedes=first["id"]).json()["can_change"] is False


@pytest.mark.django_db
def test_a_segmentation_cannot_supersede_an_annotation(client, project, ct):
    annotator = _member(project)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()

    response = _save(client, annotator, _seg_for(ct), [ct.series], supersedes=first["id"])

    assert response.status_code == 400


# --- retire ----------------------------------------------------------------


def _retire(client, user, object_id):
    client.force_login(user)
    return client.post(f"{OBJECTS_URL}/{object_id}/retire")


@pytest.mark.django_db
def test_author_retires_own_object_and_it_is_audited(client, project, ct):
    annotator = _member(project)
    saved = _save(client, annotator, _sr_for(ct), [ct.series]).json()

    response = _retire(client, annotator, saved["id"])

    assert response.status_code == 200
    assert response.json()["retired"] is True
    assert AuditLog.objects.filter(event_type="annotation_retired", user=annotator).count() == 1
    # retired, not deleted
    assert DicomSeries.objects.filter(series_instance_uid=saved["series_instance_uid"]).exists()


@pytest.mark.django_db
def test_retiring_a_superseded_version_is_409_with_the_head(client, project, ct):
    annotator = _member(project)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    second = _save(client, annotator, _sr_for(ct), [ct.series], supersedes=first["id"]).json()

    response = _retire(client, annotator, first["id"])

    assert response.status_code == 409
    assert response.json()["head"]["id"] == second["id"]


@pytest.mark.django_db
def test_a_retired_head_cannot_be_superseded(client, project, ct):
    annotator = _member(project)
    saved = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    _retire(client, annotator, saved["id"])

    response = _save(client, annotator, _sr_for(ct), [ct.series], supersedes=saved["id"])

    assert response.status_code == 409
    assert response.json()["head"]["retired"] is True


# --- roles, Sites and visibility ------------------------------------------


@pytest.mark.django_db
def test_role_without_authoring_rights_cannot_save(client, project, ct):
    response = _save(client, _member(project, PROJECT_ROLE_CONTRIBUTOR), _sr_for(ct), [ct.series])

    assert response.status_code == 403


@pytest.mark.django_db
def test_user_without_visibility_gets_404(client, project, ct):
    outsider = _user()

    assert _save(client, outsider, _sr_for(ct), [ct.series]).status_code == 404


@pytest.mark.django_db
def test_unknown_source_series_is_404(client, project, ct):
    response = _save(client, _member(project), _sr_for(ct), [DicomSeries(series_instance_uid="2.25.404")])

    assert response.status_code == 404


@pytest.mark.django_db
def test_annotator_cannot_supersede_or_retire_another_authors_work(client, project, ct):
    first = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    other = _member(project)

    assert _save(client, other, _sr_for(ct), [ct.series], supersedes=first["id"]).status_code == 403
    assert _retire(client, other, first["id"]).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_PI, PROJECT_ROLE_ADMIN])
def test_pi_and_admin_change_anyones_work(client, project, ct, role_name):
    first = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    overseer = _member(project, role_name)

    second = _save(client, overseer, _sr_for(ct), [ct.series], supersedes=first["id"])
    assert second.status_code == 201
    assert _retire(client, overseer, second.json()["id"]).status_code == 200


@pytest.mark.django_db
def test_site_pi_changes_anyones_work_only_at_its_sites(client, project, ct):
    site_a = Clinic.objects.create(clinic_code="A", clinic_name="Site A")
    site_b = Clinic.objects.create(clinic_code="B", clinic_name="Site B")
    _consent_at(ct.series.study.study_participant, project, site_a)
    first = _save(client, _member(project), _sr_for(ct), [ct.series]).json()

    site_b_pi = _member(project, PROJECT_ROLE_SITE_PI, clinic=site_b)
    assert _retire(client, site_b_pi, first["id"]).status_code == 404
    site_a_pi = _member(project, PROJECT_ROLE_SITE_PI, clinic=site_a)
    assert _retire(client, site_a_pi, first["id"]).status_code == 200


@pytest.mark.django_db
def test_site_pi_elsewhere_with_a_global_annotator_role_cannot_change_others_work(client, project, ct):
    site_a = Clinic.objects.create(clinic_code="A", clinic_name="Site A")
    site_b = Clinic.objects.create(clinic_code="B", clinic_name="Site B")
    _consent_at(ct.series.study.study_participant, project, site_a)
    first = _save(client, _member(project), _sr_for(ct), [ct.series]).json()
    user = _member(project, PROJECT_ROLE_SITE_PI, clinic=site_b)
    _grant(user, project, PROJECT_ROLE_ANNOTATOR)

    assert _retire(client, user, first["id"]).status_code == 403


@pytest.mark.django_db
def test_annotator_restricted_to_another_site_gets_404(client, project, ct):
    site_a = Clinic.objects.create(clinic_code="A", clinic_name="Site A")
    site_b = Clinic.objects.create(clinic_code="B", clinic_name="Site B")
    _consent_at(ct.series.study.study_participant, project, site_a)

    response = _save(client, _member(project, clinic=site_b), _sr_for(ct), [ct.series])

    assert response.status_code == 404


# --- list --------------------------------------------------------------------


def _list(client, user, participant, **params):
    client.force_login(user)
    return client.get(OBJECTS_URL, {"participant": str(participant.pk), **params})


@pytest.mark.django_db
def test_list_shows_chain_heads_with_history(client, project, ct):
    annotator = _member(project)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    second = _save(client, annotator, _sr_for(ct), [ct.series], supersedes=first["id"]).json()
    seg = _save(client, annotator, _seg_for(ct), [ct.series]).json()

    response = _list(client, annotator, ct.series.study.study_participant, series=ct.series.series_instance_uid)

    assert response.status_code == 200
    chains = {item["id"]: item for item in response.json()}
    assert set(chains) == {second["id"], seg["id"]}
    assert [version["version"] for version in chains[second["id"]]["history"]] == [1, 2]
    assert chains[second["id"]]["can_change"] is True


@pytest.mark.django_db
def test_list_filters_by_source_series(client, project, ct):
    annotator = _member(project)
    _save(client, annotator, _sr_for(ct), [ct.series])

    response = _list(client, annotator, ct.series.study.study_participant, series="2.25.999")

    assert response.json() == []


@pytest.mark.django_db
def test_retired_objects_are_listed_only_for_those_who_may_retire(client, project, ct):
    author = _member(project)
    saved = _save(client, author, _sr_for(ct), [ct.series]).json()
    _retire(client, author, saved["id"])
    participant = ct.series.study.study_participant

    assert _list(client, author, participant).json() == []
    assert [item["id"] for item in _list(client, author, participant, include_retired="true").json()] == [saved["id"]]
    other_annotator = _member(project)
    assert _list(client, other_annotator, participant, include_retired="true").json() == []
    viewer = _member(project, PROJECT_ROLE_CONTRIBUTOR)
    assert _list(client, viewer, participant, include_retired="true").json() == []


@pytest.mark.django_db
def test_list_of_an_invisible_participant_is_404(client, project, ct):
    assert _list(client, _user(), ct.series.study.study_participant).status_code == 404


# --- ingested objects ------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(("builder", "kind"), [(build_viewer_seg, "segmentation"), (build_viewer_sr, "annotation")])
def test_ingested_sr_and_seg_get_provenance_without_author(client, project, ct, tmp_path, builder, kind):
    # As exported by another tool: original (not pseudonymized) UIDs of the CT
    extra = {"referenced_study_uid": "1.2.9999.42.1.1001"} if builder is build_viewer_sr else {}
    raw = builder(referenced_series_uid="1.2.9999.42.1.1002", referenced_sop_uid="1.2.9999.42.1.1003", **extra)

    derived = _ingest(project, tmp_path, raw, "derived.dcm")

    pi = _member(project, PROJECT_ROLE_PI)
    chains = _list(client, pi, ct.series.study.study_participant).json()
    assert len(chains) == 1
    assert chains[0]["series_instance_uid"] == derived.series.series_instance_uid
    assert chains[0]["kind"] == kind
    assert chains[0]["source"] == "ingested"
    assert chains[0]["author"] is None
    assert chains[0]["source_series_uids"] == [ct.series.series_instance_uid]
    assert chains[0]["can_change"] is True


@pytest.mark.django_db
def test_ingested_objects_are_changed_only_by_pi_site_pi_or_admin(client, project, ct, tmp_path):
    raw = build_viewer_seg(referenced_series_uid="1.2.9999.42.1.1002", referenced_sop_uid="1.2.9999.42.1.1003")
    _ingest(project, tmp_path, raw, "derived.dcm")
    annotator = _member(project)
    head = _list(client, annotator, ct.series.study.study_participant).json()[0]

    assert head["can_change"] is False
    assert _retire(client, annotator, head["id"]).status_code == 403


@pytest.mark.django_db
def test_metadata_backfill_leaves_viewer_saved_objects_alone(client, project, ct):
    from MiqaResearch.tasks.dicom_handling.metadata_backfill import resanitize_dicom_metadata

    saved = _save(client, _member(project), _seg_for(ct), [ct.series]).json()

    resanitize_dicom_metadata.call()

    dcm_file = DicomFile.objects.get(series__series_instance_uid=saved["series_instance_uid"])
    assert dcm_file.metadata["ReferencedSeriesSequence"][0]["SeriesInstanceUID"] == ct.series.series_instance_uid
    assert dcm_file.metadata["SeriesInstanceUID"] == saved["series_instance_uid"]


@pytest.mark.django_db
def test_wado_metadata_serves_a_viewer_saved_object_without_hashing_its_uids_again(client, project, ct):
    from tests.client_binding_helpers import bound_client

    saved = _save(client, _member(project), _seg_for(ct), [ct.series]).json()
    bound_client(project, token="ann-wado")
    client.logout()

    response = client.get(
        f"/api/v1/dicom/studies/{ct.series.study.study_instance_uid}/series/{saved['series_instance_uid']}/metadata",
        HTTP_AUTHORIZATION="Bearer ann-wado",
    )

    assert response.status_code == 200, response.content
    (instance,) = response.json()
    assert instance["0020000E"]["Value"] == [saved["series_instance_uid"]]
    assert instance["0020000D"]["Value"] == [ct.series.study.study_instance_uid]
    referenced = instance["00081115"]["Value"][0]  # ReferencedSeriesSequence
    assert referenced["0020000E"]["Value"] == [ct.series.series_instance_uid]


# --- Data Kinds ------------------------------------------------------------


@pytest.mark.parametrize(("modality", "data_kind"), [
    ("SR", DATA_KIND_ANNOTATIONS), ("ANN", DATA_KIND_ANNOTATIONS),
    ("SEG", DATA_KIND_SEGMENTATIONS), ("RTSTRUCT", DATA_KIND_SEGMENTATIONS),
    ("CT", DATA_KIND_DICOM_SERIES), ("SM", DATA_KIND_DICOM_SERIES), (None, DATA_KIND_DICOM_SERIES),
])
def test_data_kind_is_split_by_modality(modality, data_kind):
    assert data_kind_for_modality(modality) == data_kind


@pytest.mark.django_db
def test_data_kind_counts_chain_heads_and_sizes_all_versions(client, project, ct, tmp_path):
    annotator = _member(project)
    first = _save(client, annotator, _sr_for(ct), [ct.series]).json()
    _save(client, annotator, _sr_for(ct), [ct.series], supersedes=first["id"])
    retired = _save(client, annotator, _seg_for(ct), [ct.series]).json()
    _retire(client, annotator, retired["id"])
    _ingest(project, tmp_path, build_viewer_seg(
        referenced_series_uid="1.2.9999.42.1.1002", referenced_sop_uid="1.2.9999.42.1.1003"), "ingested.dcm")
    participant_series = DicomSeries.objects.filter(study__study_participant=ct.series.study.study_participant)

    imaging = data_kind_totals(DATA_KIND_DICOM_SERIES, participant_series)
    annotations = data_kind_totals(DATA_KIND_ANNOTATIONS, participant_series)
    segmentations = data_kind_totals(DATA_KIND_SEGMENTATIONS, participant_series)

    assert imaging.count == 1
    assert annotations.count == 1
    assert segmentations.count == 1
    sr_sizes = [series.file_size_in_mb for series in participant_series.filter(modality="SR")]
    assert len(sr_sizes) == 2
    assert annotations.size_in_mb == pytest.approx(sum(sr_sizes))
    assert segmentations.size_in_mb == pytest.approx(
        sum(series.file_size_in_mb for series in participant_series.filter(modality="SEG")))

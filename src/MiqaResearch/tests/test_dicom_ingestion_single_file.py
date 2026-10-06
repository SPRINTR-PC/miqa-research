"""Single-file DICOM ingestion (#119) — exercises the top-level pipeline seam
`run_ingestion` directly, per the #98 testing decisions: assertions cover what
ends up in the database/storage and what the run's report says, never internal
stage call sequences.
"""
from datetime import UTC, datetime

import pytest

from MiqaResearch.data.models import DicomFile, DicomSeries, DicomStudy, ResearchProject, StudyParticipant
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, build_generic_dataset, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    """#120: local sources must sit inside the configured allow-list — allow this test's tmp_path."""
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]

@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Ingestion single-file project", description="Project for #119 tests")


def test_ingestion_creates_linked_record_hierarchy_for_new_participant(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    result = report.results[0]
    assert result.outcome == "ingested"
    assert result.error is None

    # One participant, matched/created for the file's patient identifier
    assert StudyParticipant.objects.count() == 1
    participant = StudyParticipant.objects.get()
    assert participant.research_project == research_project
    assert participant.person_source_value == "P1001"  # DEFAULT_PATIENT_ID in the shared format

    # Study/Series/File hierarchy, all linked to that participant
    assert DicomStudy.objects.count() == 1
    assert DicomSeries.objects.count() == 1
    assert DicomFile.objects.count() == 1
    dcm_file = DicomFile.objects.get()
    assert dcm_file.series.study.study_participant == participant
    assert dcm_file.research_project == research_project
    # Study datetime comes from the file's StudyDate/StudyTime tags
    assert dcm_file.series.study.study_datetime == datetime(2024, 3, 15, 10, 15, 0, 123456, tzinfo=UTC)


def test_created_records_carry_pseudonymized_uids_never_originals(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    ds = build_ct_image()
    src = write_dicom(ds, tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    study = dcm_file.series.study
    # Never the file's original UIDs ...
    assert study.study_instance_uid != ds.StudyInstanceUID
    assert dcm_file.series.series_instance_uid != ds.SeriesInstanceUID
    assert dcm_file.sop_instance_uid != ds.SOPInstanceUID
    assert dcm_file.frame_of_reference_uid != ds.FrameOfReferenceUID
    # ... but the project's deterministic HashUID pseudonyms
    from helpers.dicom_uid import pseudonymize_uid

    assert study.study_instance_uid == pseudonymize_uid(ds.StudyInstanceUID, research_project)
    assert dcm_file.series.series_instance_uid == pseudonymize_uid(ds.SeriesInstanceUID, research_project)
    assert dcm_file.sop_instance_uid == pseudonymize_uid(ds.SOPInstanceUID, research_project)
    assert dcm_file.frame_of_reference_uid == pseudonymize_uid(ds.FrameOfReferenceUID, research_project)
    # The report carries the same pseudonymized SOP Instance UID
    assert report.results[0].sop_instance_uid == dcm_file.sop_instance_uid


def test_pseudonyms_deterministic_within_project_and_distinct_across_projects(db, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    project_a = ResearchProject.objects.create(name="Pseudo A", description="a")
    project_b = ResearchProject.objects.create(name="Pseudo B", description="b")
    source = build_ct_image()
    src = write_dicom(source, tmp_path / "ct1.dcm")

    report_a = run_ingestion(project_a, src)
    assert report_a.counts["ingested"] == 1
    file_a = DicomFile.objects.get(series__study__study_participant__research_project=project_a)
    # Second file with the same source UIDs in the same project -> same pseudonyms
    same_study_src = build_ct_image(sop_instance_uid="1.2.9999.42.1.1099")
    src2 = write_dicom(same_study_src, tmp_path / "ct2.dcm")
    report_a2 = run_ingestion(project_a, src2)
    file_a2 = DicomFile.objects.exclude(pk=file_a.pk).get()
    assert report_a2.counts["ingested"] == 1
    assert file_a2.series.study.study_instance_uid == file_a.series.study.study_instance_uid
    assert file_a2.series.series_instance_uid == file_a.series.series_instance_uid

    # Same source file in another project -> different pseudonyms
    report_b = run_ingestion(project_b, src)
    file_b = DicomFile.objects.get(series__study__study_participant__research_project=project_b)
    assert report_b.counts["ingested"] == 1
    assert file_b.sop_instance_uid != file_a.sop_instance_uid
    assert file_b.series.study.study_instance_uid != file_a.series.study.study_instance_uid


def test_standard_image_geometry_populated_from_file_tags(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    assert dcm_file.image_orientation_patient == [1.0, 0.0, 0.0]
    assert dcm_file.image_position_patient == [-10.0, -20.0, 50.5]
    assert dcm_file.pixel_spacing == [0.5, 0.5]
    assert dcm_file.contains_burned_in_annotations is False


def test_metadata_captures_other_tags_with_phi_removed_first(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    metadata = DicomFile.objects.get().metadata
    # Non-PHI tags survive (DS values are read back as numbers by pydicom)
    assert metadata["KVP"] == 120.0
    assert metadata["BodyPartExamined"] == "HEAD"
    assert metadata["InstitutionName"] == "FAKE MEDICAL CENTER"
    # The defined PHI-bearing tags are gone
    for phi_keyword in (
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "ReferringPhysicianName",
        "OtherPatientIDs",
        "PatientMotherBirthName",
    ):
        assert phi_keyword not in metadata, f"PHI tag {phi_keyword} leaked into metadata"


def test_metadata_uid_tags_are_pseudonymized(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    ds = build_ct_image()
    src = write_dicom(ds, tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    metadata = dcm_file.metadata
    assert metadata["StudyInstanceUID"] == dcm_file.series.study.study_instance_uid
    assert metadata["SeriesInstanceUID"] == dcm_file.series.series_instance_uid
    assert metadata["SOPInstanceUID"] == dcm_file.sop_instance_uid
    assert metadata["FrameOfReferenceUID"] == dcm_file.frame_of_reference_uid
    # No original UID survives anywhere in the retained metadata
    import json

    dump = json.dumps(metadata)
    for original in (ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.SOPInstanceUID, ds.FrameOfReferenceUID):
        assert original not in dump


def test_nested_uid_references_are_pseudonymized_per_value(research_project, tmp_path, settings):
    """UIDs nested in sequences (e.g. ReferencedImageSequence items) must each get
    their own deterministic pseudonym — not the file's own — so cross-references
    stay distinguishable (#116 story 27)."""
    from pydicom.dataset import Dataset as Item

    from helpers.dicom_uid import pseudonymize_uid

    settings.MEDIA_ROOT = tmp_path / "media"
    ds = build_ct_image()
    item = Item()
    item.SOPInstanceUID = "1.2.9999.42.1.7777"
    item.StudyInstanceUID = ds.StudyInstanceUID
    item.SeriesInstanceUID = ds.SeriesInstanceUID
    ds.add_new(0x00081140, "SQ", [item])  # ReferencedImageSequence
    src = write_dicom(ds, tmp_path / "ct_ref.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    metadata = DicomFile.objects.get().metadata
    ref = metadata["ReferencedImageSequence"][0]
    # The referenced SOP instance gets its OWN pseudonym, distinct from the file's
    assert ref["SOPInstanceUID"] == pseudonymize_uid("1.2.9999.42.1.7777", research_project)
    assert ref["SOPInstanceUID"] != DicomFile.objects.get().sop_instance_uid
    # Same-source study/series references keep the file's own pseudonyms
    assert ref["StudyInstanceUID"] == pseudonymize_uid(ds.StudyInstanceUID, research_project)
    import json

    dump = json.dumps(metadata)
    assert "1.2.9999.42.1.7777" not in dump


def test_phi_inside_sequences_is_stripped_from_metadata(research_project, tmp_path, settings):
    """PHI-bearing tags nested inside sequences must be stripped too — the dump
    must never stringify a sequence whole (that would leak nested PHI verbatim)."""
    import json

    from pydicom.dataset import Dataset as Item

    settings.MEDIA_ROOT = tmp_path / "media"
    ds = build_ct_image()
    item = Item()
    item.PhysicianOfRecord = "EVA^LEVY"  # PHI tag nested in a sequence
    item.RequestedProcedureDescription = "CT HEAD"
    ds.add_new(0x00400275, "SQ", [item])  # RequestAttributesSequence
    src = write_dicom(ds, tmp_path / "ct_sq.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    metadata = DicomFile.objects.get().metadata
    attrs = metadata["RequestAttributesSequence"][0]
    assert attrs["RequestedProcedureDescription"] == "CT HEAD"
    assert "PhysicianOfRecord" not in attrs
    assert "EVA^LEVY" not in json.dumps(metadata)


def test_model_accepts_three_value_orientation_from_pipeline(research_project, tmp_path, settings):
    """The geometry the pipeline writes (3-valued orientation, per PS3.3) must be
    accepted by the model itself, not just by the permissive DB column."""
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")
    report = run_ingestion(research_project, src)
    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    dcm_file.full_clean(exclude=["file"])


def test_new_participant_demographics_populated_from_file(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    participant = StudyParticipant.objects.get()
    assert participant.name == "DOE^JANE"
    assert participant.year_of_birth == 1975
    assert participant.month_of_birth == 1
    assert participant.day_of_birth == 31
    assert participant.gender == "F"
    # Pseudonymous alias in the existing consent-enrollment style
    assert len(participant.alias1.split()) == 3
    # The report references the participant only by its pseudonymous alias
    assert report.results[0].study_participant_alias == participant.alias1


def test_reingest_for_existing_participant_never_overwrites_demographics(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    existing = StudyParticipant.objects.create(
        alias1="Pre Existing Cat",
        person_source_value="P1001",  # stored in the shared format, as after migration 0026
        name="Different^Name",
        year_of_birth=1980,
        month_of_birth= 5,
        day_of_birth=5,
        gender="M",
        research_project=research_project,
    )
    src = write_dicom(
        build_ct_image(patient_name="DOE^JANE", patient_birth_date="19750131", patient_sex="F"),
        tmp_path / "ct1.dcm",
    )

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    existing.refresh_from_db()
    assert StudyParticipant.objects.count() == 1
    assert existing.name == "Different^Name"
    assert existing.year_of_birth == 1980
    assert existing.month_of_birth == 5
    assert existing.day_of_birth == 5
    assert existing.gender == "M"
    # The new study hangs off the pre-existing participant
    assert DicomStudy.objects.get().study_participant == existing


def test_file_stored_locally_and_retrievable_via_wado_rs(research_project, tmp_path, settings, client):
    # The local .env's MIRES_DEBUG=1 registers the debug toolbar at settings-import
    # time while pytest forces DEBUG off — strip its middleware so requests resolve.
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")
    raw_bytes = src.read_bytes()

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    dcm_file = DicomFile.objects.get()
    # Stored locally under MEDIA_ROOT and byte-identical to the source
    assert (tmp_path / "media").exists()
    with dcm_file.file.open("rb") as stored:
        assert stored.read() == raw_bytes

    # Retrievable over the existing WADO-RS instance endpoint using only the
    # pseudonymized UIDs visible in the database
    from datetime import timedelta

    from django.utils import timezone
    from oauth2_provider.models import AccessToken, Application

    application = Application.objects.create(
        name="wado-test", user=None, client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
    )
    AccessToken.objects.create(
        token="test-token-123", application=application, user=None, scope="read",
        expires=timezone.now() + timedelta(hours=1),
    )
    url = (
        f"/api/v1/dicom/studies/{dcm_file.series.study.study_instance_uid}"
        f"/series/{dcm_file.series.series_instance_uid}/instances/{dcm_file.sop_instance_uid}"
    )
    response = client.get(url, HTTP_AUTHORIZATION="Bearer test-token-123")
    assert response.status_code == 200
    assert raw_bytes in response.content


def test_file_without_patient_id_is_per_file_error(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    ds = build_ct_image()
    del ds.PatientID
    src = write_dicom(ds, tmp_path / "noid.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    result = report.results[0]
    assert "patient identifier" in result.error
    assert StudyParticipant.objects.count() == 0
    assert DicomFile.objects.count() == 0


def test_non_dicom_file_is_per_file_error(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = tmp_path / "notdicom.bin"
    src.write_bytes(b"this is not a dicom file" * 100)

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    assert report.results[0].error == "not a DICOM file"
    assert DicomFile.objects.count() == 0
    assert StudyParticipant.objects.count() == 0


def test_reingesting_same_file_skips_duplicate(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    first = run_ingestion(research_project, src)
    second = run_ingestion(research_project, src)

    assert first.counts["ingested"] == 1
    assert second.counts == {"ingested": 0, "skipped_duplicate": 1, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 1
    assert DicomSeries.objects.count() == 1
    series = DicomSeries.objects.get()
    assert series.file_size_in_mb is not None
    # The skip must not double-count the series' accumulated size
    assert series.file_size_in_mb < len(src.read_bytes()) * 2 / (1024 * 1024)


def test_non_standard_sop_class_still_ingested_via_generic_handler(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_generic_dataset(), tmp_path / "dose_sr.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    dcm_file = DicomFile.objects.get()
    # Generic handler: no image geometry, but tags still captured
    assert dcm_file.image_orientation_patient is None
    assert dcm_file.image_position_patient is None
    assert dcm_file.pixel_spacing is None
    assert dcm_file.metadata["XRayTubeCurrent"] == 2.5


def test_file_without_preamble_still_ingested(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "nopreamble.dcm", with_preamble=False)

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 1


def test_second_file_same_study_and_series_matches_existing_records(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    first = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")
    second = write_dicom(
        build_ct_image(sop_instance_uid="1.2.9999.42.1.2002", series_description="PHASE_2"),
        tmp_path / "ct2.dcm",
    )

    run_ingestion(research_project, first)
    report = run_ingestion(research_project, second)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomStudy.objects.count() == 1
    assert DicomSeries.objects.count() == 1
    assert DicomFile.objects.count() == 2
    # Series aggregate accumulates across files
    series = DicomSeries.objects.get()
    expected = (len(first.read_bytes()) + len(second.read_bytes())) / (1024 * 1024)
    assert abs(series.file_size_in_mb - expected) < 1e-9


def test_standard_image_without_frame_of_reference_uid_ingests(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(frame_of_reference_uid=None), tmp_path / "ct_nofor.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    dcm_file = DicomFile.objects.get()
    assert dcm_file.frame_of_reference_uid is None
    assert dcm_file.image_orientation_patient == [1.0, 0.0, 0.0]


def test_partial_birth_date_populates_only_known_parts(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(patient_birth_date="1975"), tmp_path / "ct_partial_dob.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    participant = StudyParticipant.objects.get()
    assert participant.year_of_birth == 1975
    assert participant.month_of_birth is None
    assert participant.day_of_birth is None


def test_truncated_dicom_file_is_per_file_error(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "truncated.dcm")
    src.write_bytes(src.read_bytes()[: max(0, len(src.read_bytes()) - 300)])

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    assert DicomFile.objects.count() == 0

from datetime import date

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlJobInput,
    EtlLocationGrant,
    EtlProcessedFile,
    EtlProjectSettings,
    EtlScript,
    EtlScriptVersion,
    Measurement,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
    VisitOccurrence,
)
from MiqaResearch.data.models.etl_script import MAX_ETL_SCRIPT_SOURCE_BYTES


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="ETL test project", description="ETL model tests")


@pytest.fixture
def etl_script(research_project):
    return EtlScript.objects.create(name="Test script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)


@pytest.fixture
def etl_script_version(etl_script):
    return EtlScriptVersion.objects.create(
        script=etl_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"print('hi')", content_type="text/x-python"),
        sha256="0" * 64,
    )


@pytest.fixture
def pipeline_binding(research_project, etl_script_version):
    return PipelineBinding.objects.create(
        project=research_project,
        source_bucket="incoming",
        source_prefix="redcap/",
        script_version=etl_script_version,
        raw_bucket="raw",
        raw_prefix="redcap/",
    )


@pytest.fixture
def etl_job(pipeline_binding, etl_script_version):
    return EtlJob.objects.create(binding=pipeline_binding, script_version=etl_script_version)


@pytest.fixture
def study_participant(research_project):
    return StudyParticipant.objects.create(alias1="ETL-P001", research_project=research_project)


@pytest.fixture
def concept(db):
    return Concept.objects.create(
        concept_name="Body weight",
        vocabulary_id="LOINC",
        concept_class_id="Clinical Observation",
        concept_code="29463-7",
        valid_start_date=date(2000, 1, 1),
        valid_end_date=date(2099, 12, 31),
    )


# --- PipelineBinding: unique on (source_bucket, source_prefix) ---------

@pytest.mark.django_db
def test_pipeline_binding_rejects_duplicate_source_bucket_and_prefix(
    pipeline_binding, research_project, etl_script_version
):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PipelineBinding.objects.create(
                project=research_project,
                source_bucket=pipeline_binding.source_bucket,
                source_prefix=pipeline_binding.source_prefix,
                script_version=etl_script_version,
                raw_bucket="raw-2",
                raw_prefix="redcap-2/",
            )


@pytest.mark.django_db
def test_pipeline_binding_allows_same_bucket_with_a_different_prefix(
    pipeline_binding, research_project, etl_script_version
):
    other = PipelineBinding.objects.create(
        project=research_project,
        source_bucket=pipeline_binding.source_bucket,
        source_prefix="other-prefix/",
        script_version=etl_script_version,
        raw_bucket="raw-2",
        raw_prefix="other-prefix/",
    )

    assert other.pk != pipeline_binding.pk


# --- EtlScriptVersion: immutable + 256 KB cap ---------------------------

@pytest.mark.django_db
def test_etl_script_version_cannot_be_updated_after_creation(etl_script_version):
    etl_script_version.sha256 = "1" * 64

    with pytest.raises(ValidationError):
        etl_script_version.save()


@pytest.mark.django_db
def test_etl_script_version_rejects_source_file_over_256kb(etl_script):
    oversized = EtlScriptVersion(
        script=etl_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"x" * (MAX_ETL_SCRIPT_SOURCE_BYTES + 1)),
        sha256="0" * 64,
    )

    with pytest.raises(ValidationError):
        oversized.full_clean()


@pytest.mark.django_db
def test_etl_script_version_accepts_source_file_at_the_256kb_cap(etl_script):
    exact = EtlScriptVersion(
        script=etl_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"x" * MAX_ETL_SCRIPT_SOURCE_BYTES),
        sha256="0" * 64,
    )

    exact.full_clean()  # must not raise


@pytest.mark.django_db
def test_etl_script_version_cannot_be_bulk_updated_via_queryset(etl_script_version):
    with pytest.raises(ValidationError):
        EtlScriptVersion.objects.filter(pk=etl_script_version.pk).update(sha256="1" * 64)


# --- EtlScript: archive-only, no hard delete ----------------------------

@pytest.mark.django_db
def test_etl_script_cannot_be_hard_deleted(etl_script):
    with pytest.raises(ValidationError):
        etl_script.delete()


@pytest.mark.django_db
def test_etl_script_cannot_be_bulk_deleted_via_queryset(etl_script):
    with pytest.raises(ValidationError):
        EtlScript.objects.filter(pk=etl_script.pk).delete()


@pytest.mark.django_db
def test_deleting_a_project_with_etl_scripts_is_blocked(research_project, etl_script):
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        research_project.delete()


# --- measurement/visit_occurrence: nullable etl_job FK, SET_NULL --------

@pytest.mark.django_db
def test_deleting_etl_job_leaves_measurement_intact_with_etl_job_nulled(etl_job, study_participant, concept):
    measurement = Measurement.objects.create(
        person=study_participant,
        measurement_concept=concept,
        measurement_date=date(2026, 1, 1),
        measurement_type_concept=concept,
        etl_job=etl_job,
    )

    etl_job.delete()

    measurement.refresh_from_db()
    assert measurement.etl_job_id is None


@pytest.mark.django_db
def test_deleting_etl_job_leaves_visit_occurrence_intact_with_etl_job_nulled(etl_job, study_participant):
    visit = VisitOccurrence.objects.create(
        person=study_participant,
        visit_start_date=date(2026, 1, 1),
        visit_end_date=date(2026, 1, 2),
        etl_job=etl_job,
    )

    etl_job.delete()

    visit.refresh_from_db()
    assert visit.etl_job_id is None


# --- Remaining models: schema exists and is usable -----------------------

@pytest.mark.django_db
def test_etl_job_input_records_a_jobs_input_file(etl_job):
    job_input = EtlJobInput.objects.create(
        job=etl_job, bucket="incoming", key="redcap/export.csv", sha256="a" * 64, size_bytes=1024,
    )

    assert job_input.job_id == etl_job.id
    assert job_input.moved_at is None


@pytest.mark.django_db
def test_etl_processed_file_tracks_the_polling_ledger(pipeline_binding):
    processed = EtlProcessedFile.objects.create(
        binding=pipeline_binding, bucket="incoming", key="redcap/export.csv", etag="abc123",
    )

    assert processed.first_seen_at is not None


@pytest.mark.django_db
def test_etl_processed_file_rejects_duplicate_binding_bucket_and_key(pipeline_binding):
    EtlProcessedFile.objects.create(binding=pipeline_binding, bucket="incoming", key="redcap/export.csv")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EtlProcessedFile.objects.create(binding=pipeline_binding, bucket="incoming", key="redcap/export.csv")


@pytest.mark.django_db
def test_etl_project_settings_overrides_log_retention_for_a_project(research_project):
    settings_row = EtlProjectSettings.objects.create(project=research_project, log_retention_days=30)

    assert settings_row.project_id == research_project.id


@pytest.mark.django_db
def test_etl_location_grant_scopes_a_bucket_to_a_project(research_project):
    grant = EtlLocationGrant.objects.create(project=research_project, bucket="incoming", prefix="redcap/")

    assert grant.project_id == research_project.id


# --- Django admin registration -------------------------------------------

def test_all_etl_models_are_registered_in_django_admin():
    for model in (
        EtlScript,
        EtlScriptVersion,
        PipelineBinding,
        EtlJob,
        EtlJobInput,
        EtlProcessedFile,
        EtlProjectSettings,
        EtlLocationGrant,
    ):
        assert admin.site.is_registered(model), f"{model.__name__} is not registered in Django admin"

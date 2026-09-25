from datetime import date

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from contract.constants.etl import (
    ETL_JOB_STATUS_FAILED,
    ETL_JOB_STATUS_SUCCEEDED,
    ETL_SCRIPT_ORIGIN_CUSTOM,
    ETL_SCRIPT_ORIGIN_NATIVE,
    PIPELINE_BINDING_GROUPING_FILE,
)
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlJobInput,
    EtlLocationGrant,
    EtlPendingGroup,
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
from MiqaResearch.data.models.etl_project_settings import get_log_retention_days, get_max_script_source_bytes


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


# --- EtlScriptVersion: immutable + project-configurable size cap --------

@pytest.mark.django_db
def test_etl_script_version_cannot_be_updated_after_creation(etl_script_version):
    etl_script_version.sha256 = "1" * 64

    with pytest.raises(ValidationError):
        etl_script_version.save()


@pytest.mark.django_db
def test_etl_script_version_rejects_source_file_over_the_global_default_cap(etl_script, settings):
    oversized = EtlScriptVersion(
        script=etl_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"x" * (settings.ETL_SCRIPT_MAX_SOURCE_BYTES + 1)),
        sha256="0" * 64,
    )

    with pytest.raises(ValidationError):
        oversized.full_clean()


@pytest.mark.django_db
def test_etl_script_version_accepts_source_file_at_the_global_default_cap(etl_script, settings):
    exact = EtlScriptVersion(
        script=etl_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"x" * settings.ETL_SCRIPT_MAX_SOURCE_BYTES),
        sha256="0" * 64,
    )

    exact.full_clean()  # must not raise


@pytest.mark.django_db
def test_etl_script_version_project_override_lowers_the_effective_cap(research_project, etl_script, settings):
    EtlProjectSettings.objects.create(project=research_project, max_script_source_bytes=10)

    too_big_for_override = EtlScriptVersion(
        script=etl_script,
        version=1,
        # Well within the global default, but over this project's override.
        source=SimpleUploadedFile("script.py", b"x" * 11),
        sha256="0" * 64,
    )

    with pytest.raises(ValidationError):
        too_big_for_override.full_clean()


@pytest.mark.django_db
def test_etl_script_version_project_override_can_raise_the_effective_cap(research_project, etl_script, settings):
    EtlProjectSettings.objects.create(
        project=research_project, max_script_source_bytes=settings.ETL_SCRIPT_MAX_SOURCE_BYTES + 1000
    )

    over_global_default_but_within_override = EtlScriptVersion(
        script=etl_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"x" * (settings.ETL_SCRIPT_MAX_SOURCE_BYTES + 500)),
        sha256="0" * 64,
    )

    over_global_default_but_within_override.full_clean()  # must not raise


@pytest.mark.django_db
def test_etl_script_version_native_script_uses_the_global_default(settings):
    native_script = EtlScript.objects.create(name="Native script", origin=ETL_SCRIPT_ORIGIN_NATIVE)

    oversized = EtlScriptVersion(
        script=native_script,
        version=1,
        source=SimpleUploadedFile("script.py", b"x" * (settings.ETL_SCRIPT_MAX_SOURCE_BYTES + 1)),
        sha256="0" * 64,
    )

    with pytest.raises(ValidationError):
        oversized.full_clean()


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
def test_get_log_retention_days_falls_back_to_the_global_default_with_no_override(research_project, settings):
    settings.ETL_LOG_RETENTION_DAYS = 30
    assert get_log_retention_days(research_project) == 30


@pytest.mark.django_db
def test_get_log_retention_days_returns_the_project_override_when_set(research_project):
    EtlProjectSettings.objects.create(project=research_project, log_retention_days=7)

    assert get_log_retention_days(research_project) == 7


def test_get_log_retention_days_returns_the_global_default_for_no_project(settings):
    settings.ETL_LOG_RETENTION_DAYS = 30
    assert get_log_retention_days(None) == 30


@pytest.mark.django_db
def test_get_max_script_source_bytes_falls_back_to_the_global_default_with_no_override(research_project, settings):
    assert get_max_script_source_bytes(research_project) == settings.ETL_SCRIPT_MAX_SOURCE_BYTES


@pytest.mark.django_db
def test_get_max_script_source_bytes_returns_the_project_override_when_set(research_project):
    EtlProjectSettings.objects.create(project=research_project, max_script_source_bytes=42)

    assert get_max_script_source_bytes(research_project) == 42


def test_get_max_script_source_bytes_returns_the_global_default_for_no_project(settings):
    assert get_max_script_source_bytes(None) == settings.ETL_SCRIPT_MAX_SOURCE_BYTES


@pytest.mark.django_db
def test_etl_location_grant_scopes_a_bucket_to_a_project(research_project):
    grant = EtlLocationGrant.objects.create(project=research_project, bucket="incoming", prefix="redcap/")

    assert grant.project_id == research_project.id


# --- Orchestrator schema additions (#162) ---------------------------------

@pytest.mark.django_db
def test_etl_script_datatype_name_defaults_to_empty(etl_script):
    assert etl_script.datatype_name == ""


@pytest.mark.django_db
def test_etl_script_version_image_key_defaults_to_empty(etl_script_version):
    assert etl_script_version.image_key == ""


@pytest.mark.django_db
def test_pipeline_binding_grouping_mode_defaults_to_file(pipeline_binding):
    assert pipeline_binding.grouping_mode == PIPELINE_BINDING_GROUPING_FILE


@pytest.mark.django_db
def test_pipeline_binding_quiescence_seconds_has_a_sensible_default(pipeline_binding):
    assert pipeline_binding.quiescence_seconds == 300


@pytest.mark.django_db
def test_pipeline_binding_config_defaults_to_empty_dict(pipeline_binding):
    assert pipeline_binding.config == {}


@pytest.mark.django_db
def test_etl_job_attempt_defaults_to_one(etl_job):
    assert etl_job.attempt == 1


@pytest.mark.django_db
def test_etl_job_retry_of_defaults_to_none(etl_job):
    assert etl_job.retry_of is None


@pytest.mark.django_db
def test_etl_job_retry_of_links_to_the_original_job(etl_job):
    etl_job.status = ETL_JOB_STATUS_FAILED
    etl_job.save()

    retry = EtlJob.objects.create(
        binding=etl_job.binding, script_version=etl_job.script_version, attempt=2, retry_of=etl_job,
    )

    assert retry.retry_of_id == etl_job.id


@pytest.mark.django_db
def test_only_one_active_etl_job_per_binding_is_allowed(etl_job):
    # etl_job fixture is already status=pending (the model default) for its binding.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EtlJob.objects.create(binding=etl_job.binding, script_version=etl_job.script_version)


@pytest.mark.django_db
def test_a_second_job_is_allowed_once_the_first_is_no_longer_active(etl_job):
    etl_job.status = ETL_JOB_STATUS_SUCCEEDED
    etl_job.save()

    second = EtlJob.objects.create(binding=etl_job.binding, script_version=etl_job.script_version)

    assert second.pk != etl_job.pk


@pytest.mark.django_db
def test_etl_pending_group_tracks_quiescence_state(pipeline_binding):
    from django.utils import timezone

    group = EtlPendingGroup.objects.create(
        binding=pipeline_binding, group_key="2026-09-01", last_seen_at=timezone.now())

    assert group.binding_id == pipeline_binding.id


@pytest.mark.django_db
def test_etl_pending_group_rejects_duplicate_binding_and_group_key(pipeline_binding):
    from django.utils import timezone

    EtlPendingGroup.objects.create(binding=pipeline_binding, group_key="2026-09-01", last_seen_at=timezone.now())

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EtlPendingGroup.objects.create(
                binding=pipeline_binding, group_key="2026-09-01", last_seen_at=timezone.now())


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
        EtlPendingGroup,
    ):
        assert admin.site.is_registered(model), f"{model.__name__} is not registered in Django admin"

import json
from datetime import date
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja import Schema

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    Measurement,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
    VisitOccurrence,
)
from MiqaResearch.etl_datatypes import (
    AmbiguousParticipantReference,
    DatatypeAlreadyRegistered,
    DatatypeNotRegistered,
    EtlJobProjectMismatch,
    EtlRowError,
    UnresolvableParticipantReference,
    get_datatype,
    load_jsonl,
    register_datatype,
)
from MiqaResearch.etl_datatypes.measurement import MeasurementRowSchema
from MiqaResearch.etl_datatypes.visit_occurrence import VisitOccurrenceRowSchema


def _jsonl(*rows: dict) -> str:
    return "\n".join(json.dumps(row) for row in rows)


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="ETL datatype test project", description="")


@pytest.fixture
def other_research_project(db):
    return ResearchProject.objects.create(name="Other ETL datatype test project", description="")


@pytest.fixture
def study_participant(research_project):
    return StudyParticipant.objects.create(
        alias1="ETL-DT-P001", person_source_value="SRC001", research_project=research_project)


def _make_etl_job(project: ResearchProject, prefix: str) -> EtlJob:
    script = EtlScript.objects.create(name="Test script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script_version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"print('hi')"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix=prefix, script_version=script_version,
        raw_bucket="raw", raw_prefix=prefix)
    return EtlJob.objects.create(binding=binding, script_version=script_version)


@pytest.fixture
def etl_job(research_project):
    return _make_etl_job(research_project, "dt/")


@pytest.fixture
def other_etl_job(other_research_project):
    return _make_etl_job(other_research_project, "other-dt/")


@pytest.fixture
def measurement_concept(db):
    return Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))


@pytest.fixture
def measurement_type_concept(db):
    return Concept.objects.create(
        concept_name="Lab result", vocabulary_id="Provenance", concept_class_id="Type Concept",
        concept_code="lab-result", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))


@pytest.fixture
def visit_concept(db):
    return Concept.objects.create(
        concept_name="Outpatient visit", vocabulary_id="Visit", concept_class_id="Visit",
        concept_code="OP", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))


def _measurement_row(participant, measurement_concept, measurement_type_concept, **overrides):
    row = {
        "alias1": participant.alias1,
        "measurement_concept_id": str(measurement_concept.concept_id),
        "measurement_type_concept_id": str(measurement_type_concept.concept_id),
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
    }
    row.update(overrides)
    return row


def _visit_row(participant, visit_concept, **overrides):
    row = {
        "alias1": participant.alias1,
        "visit_concept_id": str(visit_concept.concept_id),
        "visit_start_date": "2026-01-10",
        "visit_end_date": "2026-01-10",
        "visit_source_value": "OP-VISIT",
    }
    row.update(overrides)
    return row


# --- Registry --------------------------------------------------------------

def test_measurement_and_visit_occurrence_are_registered_with_their_schemas():
    measurement_registration = get_datatype("measurement")
    visit_registration = get_datatype("visit_occurrence")

    assert measurement_registration.schema is MeasurementRowSchema
    assert visit_registration.schema is VisitOccurrenceRowSchema


def test_get_datatype_raises_for_an_unregistered_name():
    with pytest.raises(DatatypeNotRegistered):
        get_datatype("does-not-exist")


def test_register_datatype_rejects_a_second_registration_under_the_same_name():
    class DummySchema(Schema):
        pass

    with pytest.raises(DatatypeAlreadyRegistered):
        @register_datatype("measurement", DummySchema)
        def _dummy_loader(*, project, etl_job, rows):
            raise AssertionError("should never run")


# --- Loading: happy path -----------------------------------------------------

@pytest.mark.django_db
def test_load_jsonl_upserts_measurement_rows_and_stamps_etl_job(
        research_project, etl_job, study_participant, measurement_concept, measurement_type_concept):
    jsonl_text = _jsonl(_measurement_row(study_participant, measurement_concept, measurement_type_concept))

    result = load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)

    assert result.created == 1
    assert result.updated == 0
    measurement = Measurement.objects.get()
    assert measurement.person_id == study_participant.id
    assert measurement.etl_job_id == etl_job.id
    assert measurement.value_as_number == 71.5


@pytest.mark.django_db
def test_load_jsonl_upserts_visit_occurrence_rows_and_stamps_etl_job(
        research_project, etl_job, study_participant, visit_concept):
    jsonl_text = _jsonl(_visit_row(study_participant, visit_concept))

    result = load_jsonl(
        datatype_name="visit_occurrence", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)

    assert result.created == 1
    visit = VisitOccurrence.objects.get()
    assert visit.person_id == study_participant.id
    assert visit.etl_job_id == etl_job.id


@pytest.mark.django_db
def test_load_jsonl_resolves_participant_by_person_source_value(
        research_project, etl_job, study_participant, measurement_concept, measurement_type_concept):
    row = _measurement_row(study_participant, measurement_concept, measurement_type_concept)
    del row["alias1"]
    row["person_source_value"] = study_participant.person_source_value

    load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=_jsonl(row))

    assert Measurement.objects.get().person_id == study_participant.id


# --- Loading: idempotent re-run ----------------------------------------------

@pytest.mark.django_db
def test_reloading_the_same_batch_is_idempotent(
        research_project, etl_job, study_participant, measurement_concept, measurement_type_concept):
    jsonl_text = _jsonl(_measurement_row(study_participant, measurement_concept, measurement_type_concept))

    load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)
    second_result = load_jsonl(
        datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)

    assert Measurement.objects.count() == 1
    assert second_result.created == 0
    assert second_result.updated == 1


# --- Loading: unknown datatype ------------------------------------------------

@pytest.mark.django_db
def test_load_jsonl_raises_for_an_unregistered_datatype(research_project, etl_job):
    with pytest.raises(DatatypeNotRegistered):
        load_jsonl(datatype_name="not-a-datatype", project=research_project, etl_job=etl_job, jsonl_text="")


@pytest.mark.django_db
def test_load_jsonl_raises_when_etl_job_belongs_to_a_different_project(other_research_project, etl_job):
    with pytest.raises(EtlJobProjectMismatch):
        load_jsonl(
            datatype_name="measurement", project=other_research_project, etl_job=etl_job, jsonl_text="")


# --- Loading: all-or-nothing rollback ----------------------------------------

@pytest.mark.django_db
def test_load_jsonl_rejects_the_whole_batch_when_one_row_has_an_unknown_concept(
        research_project, etl_job, study_participant, measurement_concept, measurement_type_concept):
    valid_row = _measurement_row(study_participant, measurement_concept, measurement_type_concept)
    bad_row = _measurement_row(
        study_participant, measurement_concept, measurement_type_concept,
        measurement_source_value="HEIGHT", measurement_concept_id=str(uuid4()))
    jsonl_text = _jsonl(valid_row, bad_row)

    with pytest.raises(EtlRowError):
        load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)

    assert Measurement.objects.count() == 0


@pytest.mark.django_db
def test_load_jsonl_rolls_back_the_whole_batch_when_a_row_fails_schema_validation(
        research_project, etl_job, study_participant, measurement_concept, measurement_type_concept):
    valid_row = _measurement_row(study_participant, measurement_concept, measurement_type_concept)
    invalid_row = dict(valid_row)
    del invalid_row["measurement_source_value"]  # required natural-key field missing
    jsonl_text = _jsonl(valid_row, invalid_row)

    with pytest.raises(EtlRowError):
        load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)

    assert Measurement.objects.count() == 0


# --- Loading: Participant Reference resolution -------------------------------

@pytest.mark.django_db
def test_load_jsonl_rolls_back_the_whole_batch_on_an_ambiguous_participant_reference(
        research_project, etl_job, study_participant, measurement_concept, measurement_type_concept):
    StudyParticipant.objects.create(
        alias1="ETL-DT-P002", person_source_value=study_participant.person_source_value,
        research_project=research_project)
    row = _measurement_row(study_participant, measurement_concept, measurement_type_concept)
    del row["alias1"]
    row["person_source_value"] = study_participant.person_source_value
    jsonl_text = _jsonl(row)

    with pytest.raises(AmbiguousParticipantReference):
        load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=jsonl_text)

    assert Measurement.objects.count() == 0


@pytest.mark.django_db
def test_load_jsonl_rolls_back_the_whole_batch_on_an_unresolvable_participant_reference(
        research_project, etl_job, measurement_concept, measurement_type_concept):
    row = {
        "alias1": "no-such-participant",
        "measurement_concept_id": str(measurement_concept.concept_id),
        "measurement_type_concept_id": str(measurement_type_concept.concept_id),
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
    }

    with pytest.raises(UnresolvableParticipantReference):
        load_jsonl(datatype_name="measurement", project=research_project, etl_job=etl_job, jsonl_text=_jsonl(row))

    assert Measurement.objects.count() == 0


@pytest.mark.django_db
def test_load_jsonl_scopes_participant_resolution_to_the_project(
        other_research_project, other_etl_job, study_participant, measurement_concept, measurement_type_concept):
    # study_participant belongs to research_project, not other_research_project.
    row = _measurement_row(study_participant, measurement_concept, measurement_type_concept)
    del row["alias1"]
    row["person_source_value"] = study_participant.person_source_value

    with pytest.raises(UnresolvableParticipantReference):
        load_jsonl(
            datatype_name="measurement", project=other_research_project, etl_job=other_etl_job,
            jsonl_text=_jsonl(row))


@pytest.mark.django_db
def test_measurement_row_schema_rejects_neither_participant_reference_field(
        measurement_concept, measurement_type_concept):
    with pytest.raises(Exception):
        MeasurementRowSchema(
            measurement_concept_id=measurement_concept.concept_id,
            measurement_type_concept_id=measurement_type_concept.concept_id,
            measurement_date="2026-01-15",
            measurement_source_value="WEIGHT",
        )


@pytest.mark.django_db
def test_measurement_row_schema_rejects_both_participant_reference_fields(
        measurement_concept, measurement_type_concept):
    with pytest.raises(Exception):
        MeasurementRowSchema(
            alias1="ETL-DT-P001",
            person_source_value="SRC-001",
            measurement_concept_id=measurement_concept.concept_id,
            measurement_type_concept_id=measurement_type_concept.concept_id,
            measurement_date="2026-01-15",
            measurement_source_value="WEIGHT",
        )

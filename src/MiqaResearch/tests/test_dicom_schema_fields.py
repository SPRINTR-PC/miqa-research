"""
Round-trip coverage for the DICOM ingestion schema changes (#98, #117):

- DicomFile: image_position_patient, file_size_in_mb
- DicomSeries: file_size_in_mb, removal of the dead wadors_uri field
- ResearchProject: dicom_duplicate_handling, dicom_delete_originals_after_storage,
  dicom_hashuid_salt_key (encrypted at rest)
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from hypothesis import given, settings
from hypothesis import strategies as st

from helpers.db_fields import get_fernet
from MiqaResearch.data.models import DicomFile, DicomSeries, DicomStudy, ResearchProject, StudyParticipant


@pytest.fixture(autouse=True)
def fernet_key(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="DICOM schema project", description="Project for DICOM schema tests")


@pytest.fixture
def study_participant(research_project):
    return StudyParticipant.objects.create(alias1=f"alias-{uuid4().hex[:8]}", research_project=research_project)


@pytest.fixture
def dicom_study(study_participant):
    return DicomStudy.objects.create(
        study_participant=study_participant,
        study_datetime=datetime.now(UTC),
        study_instance_uid=f"1.2.840.{uuid4().int % 10**10}",
    )


@pytest.fixture
def dicom_series(dicom_study):
    return DicomSeries.objects.create(
        study=dicom_study,
        series_instance_uid=f"1.2.840.{uuid4().int % 10**10}",
    )


@pytest.fixture
def dicom_file(dicom_series, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return DicomFile.objects.create(
        series=dicom_series,
        sop_instance_uid=f"1.2.840.{uuid4().int % 10**10}",
        file=SimpleUploadedFile("instance.dcm", b"dicom-payload", content_type="application/dicom"),
        file_size_in_mb=1.0,
    )


@pytest.mark.django_db
def test_research_project_duplicate_handling_round_trips(research_project):
    research_project.dicom_duplicate_handling = "update"
    research_project.save()
    research_project.refresh_from_db()
    assert research_project.dicom_duplicate_handling == "update"


@pytest.mark.django_db
def test_research_project_duplicate_handling_defaults_to_skip(db):
    project = ResearchProject.objects.create(name="Default handling project", description="...")
    project.refresh_from_db()
    assert project.dicom_duplicate_handling == "skip"


@pytest.mark.django_db
@pytest.mark.parametrize("override", [True, False, None])
def test_research_project_delete_originals_override_round_trips(research_project, override):
    research_project.dicom_delete_originals_after_storage = override
    research_project.save()
    research_project.refresh_from_db()
    assert research_project.dicom_delete_originals_after_storage is override


@pytest.mark.django_db
def test_research_project_salt_key_round_trips(research_project):
    salt = uuid4().hex + uuid4().hex
    research_project.dicom_hashuid_salt_key = salt
    research_project.save()
    research_project.refresh_from_db()
    assert research_project.dicom_hashuid_salt_key == salt


@pytest.mark.django_db
def test_salt_key_is_encrypted_at_rest(research_project):
    salt = uuid4().hex + uuid4().hex
    research_project.dicom_hashuid_salt_key = salt
    research_project.save()

    with connection.cursor() as cursor:
        cursor.execute("SELECT dicom_hashuid_salt_key FROM mires_research_project WHERE id = %s", [research_project.id])
        raw_value = cursor.fetchone()[0]

    assert raw_value != salt
    assert salt not in raw_value
    assert get_fernet().decrypt(raw_value.encode("utf-8")).decode("utf-8") == salt


@pytest.mark.django_db
def test_salt_key_round_trip_for_arbitrary_strings(research_project):
    @settings(max_examples=10)
    @given(st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=64))
    def round_trip(salt):
        research_project.dicom_hashuid_salt_key = salt
        research_project.save()
        research_project.refresh_from_db()
        assert research_project.dicom_hashuid_salt_key == salt

    round_trip()


@pytest.mark.django_db
def test_dicom_file_geometry_and_size_round_trip(dicom_file):
    dicom_file.image_position_patient = [1.5, -2.25, 10.0]
    dicom_file.file_size_in_mb = 12.5
    dicom_file.save()
    dicom_file.refresh_from_db()
    assert dicom_file.image_position_patient == [1.5, -2.25, 10.0]
    assert dicom_file.file_size_in_mb == 12.5


@pytest.mark.django_db
def test_dicom_series_file_size_is_nullable_and_round_trips(dicom_series):
    dicom_series.refresh_from_db()
    assert dicom_series.file_size_in_mb is None

    dicom_series.file_size_in_mb = 4321.75
    dicom_series.save()
    dicom_series.refresh_from_db()
    assert dicom_series.file_size_in_mb == 4321.75


@pytest.mark.django_db
def test_dicom_series_wadors_uri_field_is_removed():
    assert not hasattr(DicomSeries, "wadors_uri")


def test_benchmark_plugin_is_usable(benchmark):
    result = benchmark(lambda: sum(range(10)))
    assert result == 45

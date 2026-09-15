from datetime import datetime, timezone

import pytest

from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.data.models.research_project import ResearchProjectClinicMap
from MiqaResearch.data.serializers.charts.base import ChartGroupingSchema
from MiqaResearch.data.serializers.charts.xy import LineChartResponseSchema, XYChartDataSchema, XYSeriesSchema
from MiqaResearch.data.serializers.participant_consent import (
    ClinicConsentHistorySchema,
    ConsentHistoryEventSchema,
    ProjectConsentHistoryByClinicSchema,
)
from MiqaResearch.readers.participant_consent_reader import (
    get_consent_history_by_clinic,
    get_consent_history_plot_by_clinic,
)


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


async def _create_project_with_consent_history() -> tuple[ResearchProject, Clinic, Clinic]:
    """
    Builds a project connected to two clinics, with signed and revoked consents spread
    across two dates for each clinic, so the reader has more than one clinic/date/count to format.
    """
    project = await ResearchProject.objects.acreate(name="Consent Format Test Project", description="desc")

    clinic_a = await Clinic.objects.acreate(clinic_name="Clinic A")
    clinic_b = await Clinic.objects.acreate(clinic_name="Clinic B")
    await ResearchProjectClinicMap.objects.acreate(project=project, clinic=clinic_a)
    await ResearchProjectClinicMap.objects.acreate(project=project, clinic=clinic_b)

    consent_type = await ParticipantConsentType.objects.acreate(
        label="Participation consent", research_project=project)

    participant_1 = await StudyParticipant.objects.acreate(alias1="consent-format-p1", research_project=project)
    participant_2 = await StudyParticipant.objects.acreate(alias1="consent-format-p2", research_project=project)
    participant_3 = await StudyParticipant.objects.acreate(alias1="consent-format-p3", research_project=project)
    participant_4 = await StudyParticipant.objects.acreate(alias1="consent-format-p4", research_project=project)

    # Clinic A: two consents signed on the same day
    await ParticipantConsent.objects.acreate(
        study_participant=participant_1, status="Signerat",
        consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        clinic=clinic_a, consent_type=consent_type,
    )
    await ParticipantConsent.objects.acreate(
        study_participant=participant_2, status="Signerat",
        consent_signed_date=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        clinic=clinic_a, consent_type=consent_type,
    )

    # Clinic B: one consent signed and later revoked on a different day
    await ParticipantConsent.objects.acreate(
        study_participant=participant_3, status="Signerat",
        consent_signed_date=datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
        consent_revoked_date=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc),
        clinic=clinic_b, consent_type=consent_type,
    )
    await ParticipantConsent.objects.acreate(
        study_participant=participant_4, status="Signerat",
        consent_signed_date=datetime(2026, 1, 3, 9, 0, tzinfo=timezone.utc),
        clinic=clinic_b, consent_type=consent_type,
    )

    return project, clinic_a, clinic_b


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_consent_history_by_clinic_should_return_a_project_consent_history_by_clinic_schema():
    # Arrange
    project, clinic_a, clinic_b = await _create_project_with_consent_history()

    # Act
    result = await get_consent_history_by_clinic(project)

    # Assert
    assert isinstance(result, ProjectConsentHistoryByClinicSchema)
    assert str(result.project_id) == str(project.id)
    assert isinstance(result.consent_data_by_clinic, list)

    clinics_by_name = {clinic_a.clinic_name: clinic_a, clinic_b.clinic_name: clinic_b}
    assert {clinic.clinic_name for clinic in result.consent_data_by_clinic} == set(clinics_by_name)

    for clinic_history in result.consent_data_by_clinic:
        assert isinstance(clinic_history, ClinicConsentHistorySchema)
        assert str(clinic_history.clinic_id) == str(clinics_by_name[clinic_history.clinic_name].id)
        assert isinstance(clinic_history.consent_history, list)
        assert len(clinic_history.consent_history) > 0

        for event in clinic_history.consent_history:
            assert isinstance(event, ConsentHistoryEventSchema)
            assert isinstance(event.consent_count, int)
            assert isinstance(event.retracted_count, int)
            assert isinstance(event.timestamp, datetime)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_consent_history_by_clinic_should_report_correct_consent_and_retracted_counts_per_clinic():
    # Arrange
    project, clinic_a, clinic_b = await _create_project_with_consent_history()

    # Act
    result = await get_consent_history_by_clinic(project)

    # Assert
    clinic_histories_by_id = {str(clinic.clinic_id): clinic for clinic in result.consent_data_by_clinic}

    clinic_a_total_consents = sum(
        event.consent_count for event in clinic_histories_by_id[str(clinic_a.id)].consent_history)
    clinic_a_total_retractions = sum(
        event.retracted_count for event in clinic_histories_by_id[str(clinic_a.id)].consent_history)
    assert clinic_a_total_consents == 2
    assert clinic_a_total_retractions == 0

    clinic_b_total_consents = sum(
        event.consent_count for event in clinic_histories_by_id[str(clinic_b.id)].consent_history)
    clinic_b_total_retractions = sum(
        event.retracted_count for event in clinic_histories_by_id[str(clinic_b.id)].consent_history)
    assert clinic_b_total_consents == 2
    assert clinic_b_total_retractions == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_consent_history_plot_by_clinic_should_return_a_line_chart_response_schema():
    # Arrange
    project, clinic_a, clinic_b = await _create_project_with_consent_history()

    # Act
    result = await get_consent_history_plot_by_clinic(project)

    # Assert
    assert isinstance(result, LineChartResponseSchema)
    assert isinstance(result.groupings, list)
    assert len(result.groupings) > 0

    for grouping in result.groupings:
        assert isinstance(grouping, ChartGroupingSchema)
        assert isinstance(grouping.data, XYChartDataSchema)
        assert isinstance(grouping.data.series, list)

        clinic_names = {clinic_a.clinic_name, clinic_b.clinic_name}
        series_names = {series.name for series in grouping.data.series}
        assert series_names == clinic_names

        for series in grouping.data.series:
            assert isinstance(series, XYSeriesSchema)
            assert isinstance(series.x, list)
            assert isinstance(series.y, list)
            assert len(series.x) == len(series.y)
            assert len(series.x) > 0
            assert all(isinstance(value, float) for value in series.y)

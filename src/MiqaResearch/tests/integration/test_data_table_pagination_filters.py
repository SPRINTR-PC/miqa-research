"""
Filter kinds the consent table does not declare (dropdown, multi-select) exercised through DataTablePagination against a
real queryset, using a synthetic Definition over ParticipantConsent.
"""
from datetime import UTC, datetime

import pytest
from django.test import RequestFactory
from ninja.errors import HttpError

from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.data.serializers.data_table_definition import (
    DataTableColumn,
    DataTableDefinition,
    DataTableFilter,
    DataTableSource,
)
from MiqaResearch.interfaces.http.api.pagination import DataTablePagination

_OPTIONS = (("Signerat", "Signed"), ("Återkallat", "Revoked"), ("Väntar", "Waiting"))


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


@pytest.fixture
def source(transactional_db):
    project = ResearchProject.objects.create(name="Filter Kinds", description="desc")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    clinic = Clinic.objects.create(clinic_code="FK", clinic_name="FK Clinic")
    for i, status in enumerate(["Signerat", "Signerat", "Återkallat", "Väntar"]):
        participant = StudyParticipant.objects.create(alias1=f"fk-{i}", research_project=project)
        ParticipantConsent.objects.create(
            study_participant=participant, status=status, clinic=clinic, consent_type=consent_type,
            consent_signed_date=datetime(2026, 1, 1 + i, 8, 0, tzinfo=UTC))
    definition = DataTableDefinition(columns=(
        DataTableColumn("study_participant__alias1", "Alias", "string", sortable=True),
        DataTableColumn("status", "Status", "string", filter=DataTableFilter("dropdown", _OPTIONS)),
    ))
    return DataTableSource(ParticipantConsent.objects.values(*definition.values_fields), definition)


async def _page(source, query, **params):
    request = RequestFactory().get("/table", query)
    pagination = DataTablePagination.Input(**{k: v for k, v in query.items() if k in ("page", "page_size", "sort")})
    return await DataTablePagination().apaginate_queryset(source, pagination, request, **params)


@pytest.mark.django_db(transaction=True)
async def test_dropdown_filter_is_an_exact_match(source):
    result = await _page(source, {"status": "Signerat"})

    assert result["pagination"].total_items == 2
    assert {row["status"] for row in result["rows"]} == {"Signerat"}


@pytest.mark.django_db(transaction=True)
async def test_dropdown_value_outside_the_static_options_is_a_400(source):
    with pytest.raises(HttpError) as error:
        await _page(source, {"status": "Nonsense"})

    assert error.value.status_code == 400


@pytest.mark.django_db(transaction=True)
async def test_multi_select_filter_is_comma_separated_membership(source):
    definition = DataTableDefinition(columns=(
        DataTableColumn("status", "Status", "string", filter=DataTableFilter("multi-select", _OPTIONS)),))
    members = DataTableSource(ParticipantConsent.objects.values("status"), definition)

    result = await _page(members, {"status__in": "Signerat,Väntar"})

    assert sorted(row["status"] for row in result["rows"]) == ["Signerat", "Signerat", "Väntar"]


@pytest.mark.django_db(transaction=True)
async def test_view_params_are_not_mistaken_for_unknown_keys(source):
    result = await _page(source, {"include_pid": "true", "project_id": "x"}, include_pid=True, project_id="x")

    assert result["pagination"].total_items == 4


@pytest.mark.django_db(transaction=True)
async def test_an_unknown_query_key_is_a_400_not_ignored(source):
    with pytest.raises(HttpError) as error:
        await _page(source, {"status": "Signerat", "oops": "1"})

    assert error.value.status_code == 400

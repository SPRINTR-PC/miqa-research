from datetime import datetime, timezone
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
    StudyParticipant,
)
from MiqaResearch.data.models.research_project import ResearchProjectClinicMap
from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_INVESTIGATOR,
    PROJECT_ROLE_PARTICIPANT_RECRUITER,
    PROJECT_ROLE_PI,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


@pytest.fixture
def project_with_consents(db):
    """A project with two clinics and one consent in each."""
    project = ResearchProject.objects.create(name="Role Matrix Project", description="desc")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    clinics = {}
    for code in ("A", "B"):
        clinic = Clinic.objects.create(clinic_code=f"CLINIC-{code}", clinic_name=f"Clinic {code}")
        ResearchProjectClinicMap.objects.create(project=project, clinic=clinic)
        participant = StudyParticipant.objects.create(alias1=f"p-{code}", research_project=project)
        ParticipantConsent.objects.create(
            study_participant=participant, status="Signerat", clinic=clinic, consent_type=consent_type,
            consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        )
        clinics[code] = clinic
    return project, clinics


def _user_with_role(project, role_name, clinic=None):
    user = User.objects.create_user(username=f"user-{role_name}-{uuid4().hex[:6]}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role, clinic=clinic)
    return user


def _get_table(user, project_id, **query):
    client = Client()
    client.force_login(user)
    url = reverse("api-v1:dashboard_consent_statistics_table", kwargs={"project_id": project_id})
    return client.get(url, query)


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI])
def test_project_wide_roles_are_allowed_and_see_all_clinics(project_with_consents, role_name):
    project, _ = project_with_consents
    user = _user_with_role(project, role_name)

    response = _get_table(user, project.id)

    assert response.status_code == 200
    assert response.json()["pagination"]["total_items"] == 2


@pytest.mark.django_db
def test_participant_recruiter_is_allowed_and_scoped_to_their_clinic(project_with_consents):
    project, clinics = project_with_consents
    user = _user_with_role(project, PROJECT_ROLE_PARTICIPANT_RECRUITER, clinic=clinics["A"])

    response = _get_table(user, project.id)

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total_items"] == 1
    assert [row["clinic__clinic_name"] for row in body["rows"]] == ["Clinic A"]


@pytest.mark.django_db
def test_user_with_only_a_non_qualifying_role_is_refused(project_with_consents):
    project, _ = project_with_consents
    user = _user_with_role(project, PROJECT_ROLE_INVESTIGATOR)

    response = _get_table(user, project.id)

    assert response.status_code == 403
    assert "rows" not in response.json()


@pytest.mark.django_db
def test_user_with_no_role_on_the_project_is_refused(project_with_consents):
    project, _ = project_with_consents
    user = User.objects.create_user(username="norole", password="pw")

    response = _get_table(user, project.id)

    assert response.status_code == 403


@pytest.mark.django_db
def test_superuser_is_allowed_without_any_role_and_sees_all_clinics(project_with_consents):
    project, _ = project_with_consents
    user = User.objects.create_superuser(username="root", password="pw")

    response = _get_table(user, project.id)

    assert response.status_code == 200
    assert response.json()["pagination"]["total_items"] == 2


@pytest.mark.django_db
def test_missing_project_gives_404(project_with_consents):
    project, _ = project_with_consents
    user = _user_with_role(project, PROJECT_ROLE_ADMIN)

    response = _get_table(user, uuid4())

    assert response.status_code == 404


# --- Data Table envelope, pagination and wire format -------------------------------------------------------------


def _project_with_n_consents(n):
    """A project with one clinic and n consents that all share the same signed date (ordering must still be stable)."""
    project = ResearchProject.objects.create(name=f"Paging Project {n}", description="desc")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    clinic = Clinic.objects.create(clinic_code=f"PAGING-{n}", clinic_name="Paging Clinic")
    ResearchProjectClinicMap.objects.create(project=project, clinic=clinic)
    for i in range(n):
        participant = StudyParticipant.objects.create(alias1=f"paging-{n}-{i}", research_project=project)
        ParticipantConsent.objects.create(
            study_participant=participant, status="Signerat", clinic=clinic, consent_type=consent_type,
            consent_signed_date=datetime(2026, 3, 1, 10, 15, tzinfo=timezone.utc),
        )
    return project


@pytest.fixture
def admin_of():
    def make(project):
        return _user_with_role(project, PROJECT_ROLE_ADMIN)
    return make


@pytest.mark.django_db
def test_envelope_has_snake_case_columns_rows_and_pagination_when_columns_requested(admin_of):
    project = _project_with_n_consents(3)

    body = _get_table(admin_of(project), project.id, include_columns="true").json()

    assert set(body) == {"columns", "rows", "pagination"}
    assert set(body["pagination"]) == {"page", "page_size", "total_pages", "total_items", "has_next", "has_previous"}
    columns = {column["accessor"]: column for column in body["columns"]}
    assert columns["clinic__clinic_name"]["data_type"] == "string"
    assert columns["consent_signed_date"]["data_type"] == "datetime"
    assert all(column["label"] for column in columns.values())
    assert set(body["rows"][0]) == set(columns)


@pytest.mark.django_db
def test_columns_are_omitted_unless_requested(admin_of):
    project = _project_with_n_consents(3)

    body = _get_table(admin_of(project), project.id).json()

    assert body.get("columns") is None
    assert len(body["rows"]) == 3


@pytest.mark.django_db
def test_row_keys_are_column_accessors_and_datetimes_are_iso_8601_with_utc_offset(admin_of):
    project = _project_with_n_consents(1)

    row = _get_table(admin_of(project), project.id).json()["rows"][0]

    assert row["clinic__clinic_name"] == "Paging Clinic"
    assert row["consent_signed_date"] == "2026-03-01T10:15:00+00:00"
    assert row["consent_revoked_date"] is None


@pytest.mark.django_db
def test_pages_report_totals_and_next_previous_flags_at_the_boundaries(admin_of):
    project = _project_with_n_consents(25)
    user = admin_of(project)

    first = _get_table(user, project.id, page=1, page_size=10).json()
    middle = _get_table(user, project.id, page=2, page_size=10).json()
    last = _get_table(user, project.id, page=3, page_size=10).json()

    assert first["pagination"] == {
        "page": 1, "page_size": 10, "total_pages": 3, "total_items": 25, "has_next": True, "has_previous": False}
    assert (middle["pagination"]["has_next"], middle["pagination"]["has_previous"]) == (True, True)
    assert (last["pagination"]["has_next"], last["pagination"]["has_previous"]) == (False, True)
    assert [len(page["rows"]) for page in (first, middle, last)] == [10, 10, 5]


@pytest.mark.django_db
def test_exact_multiple_of_page_size_has_no_extra_page(admin_of):
    project = _project_with_n_consents(20)

    body = _get_table(admin_of(project), project.id, page=2, page_size=10).json()

    assert body["pagination"]["total_pages"] == 2
    assert body["pagination"]["has_next"] is False


@pytest.mark.django_db
def test_empty_result_has_zero_totals_and_no_next_or_previous(admin_of):
    project = _project_with_n_consents(0)

    body = _get_table(admin_of(project), project.id).json()

    assert body["rows"] == []
    assert body["pagination"] == {
        "page": 1, "page_size": 25, "total_pages": 0, "total_items": 0, "has_next": False, "has_previous": False}


@pytest.mark.django_db
def test_paging_is_stable_when_rows_share_the_same_sort_value(admin_of):
    project = _project_with_n_consents(23)
    user = admin_of(project)

    seen = []
    for page in (1, 2, 3):
        seen += [row["study_participant__alias1"] for row in
                 _get_table(user, project.id, page=page, page_size=10).json()["rows"]]

    assert len(seen) == len(set(seen)) == 23


@pytest.mark.django_db
def test_default_page_size_is_25(admin_of):
    project = _project_with_n_consents(30)

    body = _get_table(admin_of(project), project.id).json()

    assert body["pagination"]["page_size"] == 25
    assert len(body["rows"]) == 25


@pytest.mark.django_db
@pytest.mark.parametrize("query", [
    {"page": 0}, {"page": -1}, {"page": "abc"}, {"page_size": 0}, {"page_size": 201}, {"page_size": "abc"},
])
def test_invalid_page_or_page_size_is_a_validation_error(admin_of, query):
    project = _project_with_n_consents(1)

    response = _get_table(admin_of(project), project.id, **query)

    assert response.status_code == 422


@pytest.mark.django_db
def test_maximum_page_size_is_accepted(admin_of):
    project = _project_with_n_consents(1)

    response = _get_table(admin_of(project), project.id, page_size=200)

    assert response.status_code == 200
    assert response.json()["pagination"]["page_size"] == 200


@pytest.mark.django_db
def test_dashboard_panel_template_resolves_the_table_endpoint_by_name(admin_of):
    from django.template.loader import render_to_string

    project = _project_with_n_consents(1)

    html = render_to_string("01_dashboard/_panel_consent_statistics_table.html", {"project": project})

    expected_url = reverse("api-v1:dashboard_consent_statistics_table", kwargs={"project_id": project.id})
    assert f'dataUrl="{expected_url}"' in html


# --- Sorting -------------------------------------------------------------------------------------------------------


@pytest.fixture
def sortable_project(db):
    """Consents: (clinic, status, signed day). Two share a status and a clinic to force ties."""
    project = ResearchProject.objects.create(name="Sort Project", description="desc")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    clinics = {}
    for name in ("Alpha", "Beta"):
        clinics[name] = Clinic.objects.create(clinic_code=f"SORT-{name}", clinic_name=name)
        ResearchProjectClinicMap.objects.create(project=project, clinic=clinics[name])
    for i, (clinic, status, day) in enumerate([
        ("Beta", "Signerat", 5), ("Alpha", "Signerat", 3), ("Alpha", "Återkallat", 9), ("Beta", "Signerat", 1),
    ]):
        participant = StudyParticipant.objects.create(alias1=f"sort-{i}", research_project=project)
        ParticipantConsent.objects.create(
            study_participant=participant, status=status, clinic=clinics[clinic], consent_type=consent_type,
            consent_signed_date=datetime(2026, 2, day, 8, 0, tzinfo=timezone.utc),
        )
    return project


def _column(rows, key):
    return [row[key] for row in rows]


@pytest.mark.django_db
def test_no_sort_follows_the_declared_default_of_newest_signed_first(sortable_project, admin_of):
    rows = _get_table(admin_of(sortable_project), sortable_project.id).json()["rows"]

    days = [row["consent_signed_date"][:10] for row in rows]
    assert days == ["2026-02-09", "2026-02-05", "2026-02-03", "2026-02-01"]


@pytest.mark.django_db
def test_columns_declare_sortable_and_the_default_sort(sortable_project, admin_of):
    columns = _get_table(admin_of(sortable_project), sortable_project.id, include_columns="true").json()["columns"]
    by_accessor = {column["accessor"]: column for column in columns}

    assert all(column["sortable"] for column in columns)
    assert by_accessor["consent_signed_date"]["default_sort"] == "desc"
    assert by_accessor["consent_signed_date"]["default_sort_order"] == 1
    assert by_accessor["clinic__clinic_name"]["default_sort"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("sort, expected_days", [
    ("consent_signed_date", [1, 3, 5, 9]),
    ("-consent_signed_date", [9, 5, 3, 1]),
])
def test_single_column_sort_ascending_and_descending(sortable_project, admin_of, sort, expected_days):
    rows = _get_table(admin_of(sortable_project), sortable_project.id, sort=sort).json()["rows"]

    assert [int(row["consent_signed_date"][8:10]) for row in rows] == expected_days


@pytest.mark.django_db
def test_multi_column_sort_uses_later_columns_to_break_ties(sortable_project, admin_of):
    rows = _get_table(
        admin_of(sortable_project), sortable_project.id, sort="clinic__clinic_name,-consent_signed_date").json()["rows"]

    assert [(row["clinic__clinic_name"], int(row["consent_signed_date"][8:10])) for row in rows] == [
        ("Alpha", 9), ("Alpha", 3), ("Beta", 5), ("Beta", 1)]


@pytest.mark.django_db
def test_paging_is_stable_when_the_requested_sort_keys_tie(admin_of):
    project = _project_with_n_consents(23)
    user = admin_of(project)

    seen = []
    for page in (1, 2, 3):
        seen += _column(
            _get_table(user, project.id, sort="status", page=page, page_size=10).json()["rows"],
            "study_participant__alias1")

    assert len(seen) == len(set(seen)) == 23


@pytest.mark.django_db
@pytest.mark.parametrize("sort", [
    "nonexistent",
    "-nonexistent",
    "study_participant__name",  # a PID column, not declared unless include_pid
    "consent_signed_date,nonexistent",
    "c1,c2,c3,c4,c5,c6,c7",
    "clinic_id,clinic__clinic_name,clinic__clinic_code,status,consent_signed_date,consent_revoked_date,last_updated",
])
def test_unknown_or_too_many_sort_columns_are_a_400(sortable_project, admin_of, sort):
    response = _get_table(admin_of(sortable_project), sortable_project.id, sort=sort)

    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_six_sort_columns_are_accepted(sortable_project, admin_of):
    sort = "clinic_id,clinic__clinic_name,clinic__clinic_code,status,consent_signed_date,consent_revoked_date"

    response = _get_table(admin_of(sortable_project), sortable_project.id, sort=sort)

    assert response.status_code == 200


@pytest.mark.django_db
def test_encrypted_pid_columns_are_not_sortable(sortable_project, admin_of):
    user = admin_of(sortable_project)

    columns = _get_table(user, sortable_project.id, include_columns="true", include_pid="true").json()["columns"]
    pid_columns = [column for column in columns if column["accessor"].startswith("study_participant__")
                   and column["accessor"] != "study_participant__alias1"]

    assert pid_columns and not any(column["sortable"] for column in pid_columns)
    assert _get_table(user, sortable_project.id, include_pid="true", sort="study_participant__name").status_code == 400


# --- Filtering -----------------------------------------------------------------------------------------------------


def _aliases(response):
    return sorted(row["study_participant__alias1"] for row in response.json()["rows"])


@pytest.mark.django_db
def test_text_filter_is_case_insensitive_contains(sortable_project, admin_of):
    response = _get_table(admin_of(sortable_project), sortable_project.id, clinic__clinic_name__icontains="ALP")

    assert response.status_code == 200
    assert {row["clinic__clinic_name"] for row in response.json()["rows"]} == {"Alpha"}
    assert response.json()["pagination"]["total_items"] == 2


@pytest.mark.django_db
def test_date_range_filter_is_inclusive_of_the_whole_end_day(sortable_project, admin_of):
    late = ParticipantConsent.objects.filter(consent_type__research_project=sortable_project).first()
    late.consent_signed_date = datetime(2026, 2, 5, 23, 59, 59, tzinfo=timezone.utc)
    late.save()
    user = admin_of(sortable_project)

    response = _get_table(
        user, sortable_project.id, consent_signed_date__gte="2026-02-03", consent_signed_date__lte="2026-02-05")

    # 3rd, the 5th at 08:00 and the 5th at 23:59:59 are in; the 1st and the 9th are out
    days = sorted(int(row["consent_signed_date"][8:10]) for row in response.json()["rows"])
    assert days == [3, 5, 5]
    assert any(row["consent_signed_date"].startswith("2026-02-05T23:59:59") for row in response.json()["rows"])


@pytest.mark.django_db
def test_date_range_with_only_a_start_or_only_an_end(sortable_project, admin_of):
    user = admin_of(sortable_project)

    from_the_5th = _get_table(user, sortable_project.id, consent_signed_date__gte="2026-02-05").json()["rows"]
    until_the_3rd = _get_table(user, sortable_project.id, consent_signed_date__lte="2026-02-03").json()["rows"]

    assert sorted(int(r["consent_signed_date"][8:10]) for r in from_the_5th) == [5, 9]
    assert sorted(int(r["consent_signed_date"][8:10]) for r in until_the_3rd) == [1, 3]


@pytest.mark.django_db
def test_filters_sort_and_paging_combine(sortable_project, admin_of):
    user = admin_of(sortable_project)
    common = dict(consent_signed_date__gte="2026-02-03", sort="-consent_signed_date", page_size=2)

    first = _get_table(user, sortable_project.id, page=1, **common).json()
    second = _get_table(user, sortable_project.id, page=2, **common).json()

    days = lambda body: [int(row["consent_signed_date"][8:10]) for row in body["rows"]]  # noqa: E731
    assert (days(first), days(second)) == ([9, 5], [3])
    assert first["pagination"]["total_items"] == second["pagination"]["total_items"] == 3
    assert first["pagination"]["has_next"] and not second["pagination"]["has_next"]


@pytest.mark.django_db
def test_recruiter_filtering_stays_limited_to_their_clinic(sortable_project):
    alpha = Clinic.objects.get(clinic_code="SORT-Alpha")
    recruiter = _user_with_role(sortable_project, PROJECT_ROLE_PARTICIPANT_RECRUITER, clinic=alpha)

    everything = _get_table(recruiter, sortable_project.id, clinic__clinic_name__icontains="a").json()
    asking_for_beta = _get_table(recruiter, sortable_project.id, clinic__clinic_name__icontains="beta").json()

    assert {row["clinic__clinic_name"] for row in everything["rows"]} == {"Alpha"}
    assert asking_for_beta["rows"] == []
    assert asking_for_beta["pagination"]["total_items"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize("query", [
    {"nonexistent": "x"},
    {"clinic__clinic_name": "Alpha"},  # exact is not the lookup of a text filter
    {"clinic__clinic_name__exact": "Alpha"},
    {"clinic_id": "x"},  # declared but not filterable
    {"study_participant__name__icontains": "x"},  # PID column, not declared without include_pid
    {"consent_signed_date": "2026-02-01"},  # a date-range has no exact form
    {"per_page": 10},  # the old paging parameter must not be ignored
    {"consent_signed_date__gte": "yesterday"},
    {"consent_signed_date__lte": "2026-13-01"},
])
def test_unknown_non_filterable_and_wrong_typed_filters_are_a_400_never_ignored(sortable_project, admin_of, query):
    response = _get_table(admin_of(sortable_project), sortable_project.id, **query)

    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_a_repeated_filter_key_is_a_400(sortable_project, admin_of):
    client = Client()
    client.force_login(admin_of(sortable_project))
    url = reverse("api-v1:dashboard_consent_statistics_table", kwargs={"project_id": sortable_project.id})

    response = client.get(url + "?clinic__clinic_name__icontains=a&clinic__clinic_name__icontains=b")

    assert response.status_code == 400


@pytest.mark.django_db
def test_columns_metadata_declares_the_filter_kinds(sortable_project, admin_of):
    columns = _get_table(admin_of(sortable_project), sortable_project.id, include_columns="true").json()["columns"]
    filters = {column["accessor"]: column["filter"] for column in columns}

    assert filters["clinic__clinic_name"] == {"kind": "text", "options": None}
    assert filters["consent_signed_date"]["kind"] == "date-range"
    assert filters["clinic_id"] is None


# --- PID authorization ---------------------------------------------------------------------------------------------

PID_KEYS = {"study_participant__person_source_value", "study_participant__name"}


@pytest.fixture
def pid_project(db):
    """One consent per clinic; every participant has a PID and a name (encrypted at rest)."""
    project = ResearchProject.objects.create(name="PID Project", description="desc")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    clinics = {}
    for code in ("A", "B"):
        clinic = Clinic.objects.create(clinic_code=f"PID-{code}", clinic_name=f"PID Clinic {code}")
        ResearchProjectClinicMap.objects.create(project=project, clinic=clinic)
        participant = StudyParticipant.objects.create(
            alias1=f"pid-alias-{code}", person_source_value=f"19121212-000{code}", name=f"Person {code}",
            research_project=project)
        ParticipantConsent.objects.create(
            study_participant=participant, status="Signerat", clinic=clinic, consent_type=consent_type,
            consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
        clinics[code] = clinic
    return project, clinics


def _eligible_users(project, clinics):
    return {
        "admin": _user_with_role(project, PROJECT_ROLE_ADMIN),
        "pi": _user_with_role(project, PROJECT_ROLE_PI),
        "recruiter": _user_with_role(project, PROJECT_ROLE_PARTICIPANT_RECRUITER, clinic=clinics["A"]),
        "superuser": User.objects.create_superuser(username="pid-root", password="pw"),
    }


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["admin", "pi", "recruiter", "superuser"])
def test_eligible_user_without_include_pid_gets_no_pid_in_rows_or_columns(pid_project, who):
    project, clinics = pid_project
    user = _eligible_users(project, clinics)[who]

    body = _get_table(user, project.id, include_columns="true").json()

    assert not PID_KEYS & {key for row in body["rows"] for key in row}
    assert not PID_KEYS & {column["accessor"] for column in body["columns"]}


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["admin", "pi", "recruiter", "superuser"])
def test_eligible_user_with_include_pid_gets_pid_in_rows_and_columns(pid_project, who):
    project, clinics = pid_project
    user = _eligible_users(project, clinics)[who]

    body = _get_table(user, project.id, include_columns="true", include_pid="true").json()

    assert PID_KEYS <= {column["accessor"] for column in body["columns"]}
    assert all(PID_KEYS <= set(row) for row in body["rows"])
    assert {row["study_participant__name"] for row in body["rows"]} >= {"Person A"}


@pytest.mark.django_db
def test_recruiter_sees_pid_only_for_participants_in_their_own_clinic(pid_project):
    project, clinics = pid_project
    recruiter = _eligible_users(project, clinics)["recruiter"]

    rows = _get_table(recruiter, project.id, include_pid="true").json()["rows"]

    assert [(row["study_participant__name"], row["study_participant__person_source_value"]) for row in rows] == [
        ("Person A", "19121212-000A")]


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_INVESTIGATOR, None])
@pytest.mark.parametrize("include_pid", ["true", "false"])
def test_ineligible_user_never_receives_pid_keys_and_include_pid_is_a_403(pid_project, role_name, include_pid):
    project, _ = pid_project
    user = (_user_with_role(project, role_name) if role_name
            else User.objects.create_user(username="pid-norole", password="pw"))

    response = _get_table(user, project.id, include_columns="true", include_pid=include_pid)

    assert response.status_code == 403
    body = response.json()
    assert "rows" not in body and "columns" not in body
    assert not any(key in response.content.decode() for key in PID_KEYS)
    assert "Person A" not in response.content.decode()


@pytest.mark.django_db
def test_include_pid_is_refused_with_403_for_a_table_viewer_who_may_not_see_pid(pid_project, monkeypatch):
    """The reader is the one place that knows which roles may see PID: narrowing it must not silently omit columns."""
    from MiqaResearch.readers import participant_consent_reader

    project, clinics = pid_project
    recruiter = _eligible_users(project, clinics)["recruiter"]
    monkeypatch.setattr(participant_consent_reader, "CONSENT_TABLE_PID_ROLES", (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI))

    with_pid = _get_table(recruiter, project.id, include_columns="true", include_pid="true")
    without_pid = _get_table(recruiter, project.id, include_columns="true")

    assert with_pid.status_code == 403
    assert without_pid.status_code == 200
    assert not PID_KEYS & {column["accessor"] for column in without_pid.json()["columns"]}


@pytest.mark.django_db
@pytest.mark.parametrize("include_pid", ["false", "true"])
@pytest.mark.parametrize("query", [
    {"sort": "study_participant__name"},
    {"sort": "-study_participant__person_source_value"},
    {"study_participant__name__icontains": "person"},  # encrypted: no substring matching, only exact
    {"study_participant__person_source_value__icontains": "1912"},
    {"study_participant__person_source_value_hash": "abc"},  # the hash field is an implementation detail
])
def test_pid_columns_can_never_be_sorted_or_substring_filtered(pid_project, include_pid, query):
    """Encrypted with a random IV: the database can neither order nor substring-match them, so the request is refused."""
    project, clinics = pid_project
    admin = _eligible_users(project, clinics)["admin"]

    response = _get_table(admin, project.id, include_pid=include_pid, **query)

    assert response.status_code == 400
    assert "Person A" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("column, value, expected", [
    ("study_participant__person_source_value", "19121212-000B", ["Person B"]),
    ("study_participant__name", "Person A", ["Person A"]),
    ("study_participant__name", "person a", []),  # exact means case-sensitive
    ("study_participant__name", "Person", []),  # and not a substring match
    ("study_participant__person_source_value", "19121212-9999", []),
])
def test_eligible_user_can_filter_pid_columns_by_exact_match(pid_project, column, value, expected):
    project, clinics = pid_project
    admin = _eligible_users(project, clinics)["admin"]

    body = _get_table(admin, project.id, include_pid="true", **{column: value}).json()

    assert [row["study_participant__name"] for row in body["rows"]] == expected
    assert body["pagination"]["total_items"] == len(expected)


@pytest.mark.django_db
def test_exact_pid_filter_is_refused_unless_pid_columns_are_included(pid_project):
    project, clinics = pid_project
    admin = _eligible_users(project, clinics)["admin"]

    response = _get_table(admin, project.id, study_participant__name="Person A")

    assert response.status_code == 400
    assert "Person A" not in response.content.decode()


@pytest.mark.django_db
def test_exact_pid_filter_stays_limited_to_the_recruiters_own_clinic(pid_project):
    project, clinics = pid_project
    recruiter = _eligible_users(project, clinics)["recruiter"]  # clinic A only

    own = _get_table(recruiter, project.id, include_pid="true", study_participant__name="Person A").json()
    other_clinic = _get_table(recruiter, project.id, include_pid="true", study_participant__name="Person B").json()

    assert [row["study_participant__name"] for row in own["rows"]] == ["Person A"]
    assert other_clinic["rows"] == [] and other_clinic["pagination"]["total_items"] == 0


@pytest.mark.django_db
def test_pid_columns_declare_an_exact_filter_and_are_not_sortable(pid_project):
    project, clinics = pid_project
    admin = _eligible_users(project, clinics)["admin"]

    columns = _get_table(admin, project.id, include_pid="true", include_columns="true").json()["columns"]
    pid_columns = [c for c in columns if c["accessor"] in PID_KEYS]

    assert {c["accessor"] for c in pid_columns} == PID_KEYS
    assert all(c["filter"] == {"kind": "text-exact", "options": None} and not c["sortable"] for c in pid_columns)


@pytest.mark.django_db
def test_ineligible_user_cannot_use_the_exact_pid_filter(pid_project):
    project, _ = pid_project
    user = _user_with_role(project, PROJECT_ROLE_INVESTIGATOR)

    response = _get_table(user, project.id, include_pid="true", study_participant__name="Person A")

    assert response.status_code == 403
    assert "Person A" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("query", [
    {"sort": "study_participant__name"},
    {"study_participant__name__icontains": "person"},
])
def test_ineligible_user_sorting_or_filtering_on_pid_is_refused(pid_project, query):
    project, _ = pid_project
    user = _user_with_role(project, PROJECT_ROLE_INVESTIGATOR)

    response = _get_table(user, project.id, include_pid="true", **query)

    assert 400 <= response.status_code < 500
    assert "Person A" not in response.content.decode()


@pytest.mark.django_db
def test_exact_pid_filter_with_a_non_ascii_name_combines_with_sort_and_paging(pid_project):
    project, clinics = pid_project
    participant = StudyParticipant.objects.get(alias1="pid-alias-A")
    participant.name = "Åsa Öberg"
    participant.save()  # re-saves the ciphertext and the hash
    admin = _eligible_users(project, clinics)["admin"]

    body = _get_table(
        admin, project.id, include_pid="true", study_participant__name="Åsa Öberg",
        sort="-consent_signed_date", page=1, page_size=5).json()

    assert [row["study_participant__name"] for row in body["rows"]] == ["Åsa Öberg"]


@pytest.mark.django_db
def test_empty_exact_pid_filter_is_a_400(pid_project):
    project, clinics = pid_project
    admin = _eligible_users(project, clinics)["admin"]

    assert _get_table(admin, project.id, include_pid="true", study_participant__name="").status_code == 400


@pytest.mark.django_db
def test_exact_pid_filter_is_a_503_not_a_500_when_the_hash_key_is_missing(pid_project, settings):
    project, clinics = pid_project
    admin = _eligible_users(project, clinics)["admin"]
    settings.SENSITIVE_DATA_HASH_KEY = None

    response = _get_table(admin, project.id, include_pid="true", study_participant__name="Person A")

    assert response.status_code == 503
    assert "Person A" not in response.content.decode()

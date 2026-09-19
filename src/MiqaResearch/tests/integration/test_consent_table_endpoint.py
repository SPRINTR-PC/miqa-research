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


def _get_table(user, project_id):
    client = Client()
    client.force_login(user)
    url = reverse("api-v1:dashboard_consent_statistics_table", kwargs={"project_id": project_id})
    return client.get(url)


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

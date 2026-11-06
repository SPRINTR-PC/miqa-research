"""Participant Visibility (#272): the one shared rule for which Study Participants a user may see."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Exists, OuterRef
from django.test.utils import CaptureQueriesContext

from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_ANNOTATOR,
    PROJECT_ROLE_CONTRIBUTOR,
    PROJECT_ROLE_DATA_MANAGER,
    PROJECT_ROLE_INVESTIGATOR,
    PROJECT_ROLE_PARTICIPANT_RECRUITER,
    PROJECT_ROLE_PI,
    PROJECT_ROLE_SITE_PI,
)
from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
    StudyParticipant,
)
from MiqaResearch.readers.participant_visibility import can_see_participant, visible_participants

SITE_SCOPABLE_ROLES = [
    PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_CONTRIBUTOR, PROJECT_ROLE_DATA_MANAGER, PROJECT_ROLE_INVESTIGATOR,
    PROJECT_ROLE_PARTICIPANT_RECRUITER,
]

User = get_user_model()


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


@pytest.fixture
def world(db):
    """Project with Sites A and B, one participant consented at each, plus an unconsented one."""
    project = ResearchProject.objects.create(name="Visibility", description="d")
    consent_type = ParticipantConsentType.objects.create(label="Participation", research_project=project)
    clinics = {code: Clinic.objects.create(clinic_code=f"C-{code}", clinic_name=f"Clinic {code}") for code in "AB"}
    participants = {}
    for code, clinic in clinics.items():
        participants[code] = StudyParticipant.objects.create(alias1=f"p-{code}", research_project=project)
        _consent(participants[code], clinic, consent_type)
    participants["none"] = StudyParticipant.objects.create(alias1="p-none", research_project=project)
    return project, consent_type, clinics, participants


def _consent(participant, clinic, consent_type, revoked=False):
    return ParticipantConsent.objects.create(
        study_participant=participant, status="Signerat", clinic=clinic, consent_type=consent_type,
        consent_signed_date=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        consent_revoked_date=datetime(2026, 2, 1, 9, 0, tzinfo=UTC) if revoked else None,
    )


def _user(**kwargs):
    return User.objects.create_user(username=f"u-{uuid4().hex[:8]}", password="pw", **kwargs)


def _grant(user, project, role_name, clinic=None):
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    return ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role, clinic=clinic)


def _aliases(user, project):
    return sorted(visible_participants(user, project).values_list("alias1", flat=True))


@pytest.mark.django_db
def test_superuser_sees_every_participant_of_the_project(world):
    project, _, _, _ = world

    assert _aliases(_user(is_superuser=True), project) == ["p-A", "p-B", "p-none"]


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI])
def test_admin_and_pi_with_site_assignment_still_see_all_sites(world, role_name):
    project, _, clinics, _ = world
    user = _user()
    _grant(user, project, role_name, clinic=clinics["A"])

    assert _aliases(user, project) == ["p-A", "p-B", "p-none"]


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", SITE_SCOPABLE_ROLES)
def test_other_roles_without_clinic_see_all_sites(world, role_name):
    project, _, _, _ = world
    user = _user()
    _grant(user, project, role_name)

    assert _aliases(user, project) == ["p-A", "p-B", "p-none"]


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", [*SITE_SCOPABLE_ROLES, PROJECT_ROLE_SITE_PI])
def test_role_with_clinic_sees_only_participants_consented_at_that_site(world, role_name):
    project, _, clinics, _ = world
    user = _user()
    _grant(user, project, role_name, clinic=clinics["A"])

    assert _aliases(user, project) == ["p-A"]


@pytest.mark.django_db
def test_revoked_consent_at_the_site_still_grants_visibility(world):
    project, consent_type, clinics, participants = world
    _consent(participants["none"], clinics["A"], consent_type, revoked=True)
    user = _user()
    _grant(user, project, PROJECT_ROLE_SITE_PI, clinic=clinics["A"])

    assert _aliases(user, project) == ["p-A", "p-none"]


@pytest.mark.django_db
def test_consents_of_another_projects_consent_type_do_not_count(world):
    project, _, clinics, participants = world
    other = ResearchProject.objects.create(name="Other", description="d")
    other_type = ParticipantConsentType.objects.create(label="Participation", research_project=other)
    _consent(participants["none"], clinics["A"], other_type)
    user = _user()
    _grant(user, project, PROJECT_ROLE_INVESTIGATOR, clinic=clinics["A"])

    assert _aliases(user, project) == ["p-A"]


@pytest.mark.django_db
def test_visibility_is_the_union_of_role_rows(world):
    project, _, clinics, _ = world
    user = _user()
    _grant(user, project, PROJECT_ROLE_SITE_PI, clinic=clinics["A"])
    _grant(user, project, PROJECT_ROLE_ANNOTATOR, clinic=clinics["B"])

    assert _aliases(user, project) == ["p-A", "p-B"]


@pytest.mark.django_db
def test_union_with_an_all_sites_row_sees_everything(world):
    project, _, clinics, _ = world
    user = _user()
    _grant(user, project, PROJECT_ROLE_SITE_PI, clinic=clinics["A"])
    _grant(user, project, PROJECT_ROLE_INVESTIGATOR)

    assert _aliases(user, project) == ["p-A", "p-B", "p-none"]


@pytest.mark.django_db
def test_roles_on_another_project_grant_nothing(world):
    project, _, _, _ = world
    other = ResearchProject.objects.create(name="Other", description="d")
    user = _user()
    _grant(user, other, PROJECT_ROLE_ADMIN)

    assert _aliases(user, project) == []


@pytest.mark.django_db
def test_participants_of_other_projects_are_never_visible(world):
    project, consent_type, clinics, _ = world
    other = ResearchProject.objects.create(name="Other", description="d")
    StudyParticipant.objects.create(alias1="p-other", research_project=other)

    assert _aliases(_user(is_superuser=True), project) == ["p-A", "p-B", "p-none"]


@pytest.mark.django_db
def test_can_see_participant(world):
    project, _, clinics, participants = world
    user = _user()
    _grant(user, project, PROJECT_ROLE_SITE_PI, clinic=clinics["A"])

    assert can_see_participant(user, project, participants["A"]) is True
    assert can_see_participant(user, project, participants["B"]) is False
    assert can_see_participant(user, project, participants["A"].pk) is True


@pytest.mark.django_db
def test_visible_participants_composes_as_a_single_query_subquery(world):
    project, _, clinics, participants = world
    user = _user()
    _grant(user, project, PROJECT_ROLE_SITE_PI, clinic=clinics["A"])

    with CaptureQueriesContext(connection) as ctx:
        consents = list(
            ParticipantConsent.objects.filter(
                Exists(visible_participants(user, project).filter(pk=OuterRef("study_participant")))
            ).values_list("study_participant__alias1", flat=True)
        )

    assert consents == ["p-A"]
    assert len(ctx.captured_queries) == 1


@pytest.mark.django_db
def test_site_pi_cannot_be_saved_without_a_clinic(world):
    project, _, _, _ = world
    role, _ = ResearchProjectRole.objects.get_or_create(
        name=PROJECT_ROLE_SITE_PI, defaults={"description": PROJECT_ROLE_SITE_PI})
    row = ResearchProjectUserRoleMap(user=_user(), project=project, role=role)

    with pytest.raises(ValidationError) as excinfo:
        row.full_clean()
    assert "clinic" in excinfo.value.message_dict
    with pytest.raises(ValidationError):
        row.save()
    assert not ResearchProjectUserRoleMap.objects.filter(role=role).exists()


@pytest.mark.django_db
def test_site_pi_role_is_seeded():
    assert ResearchProjectRole.objects.filter(name=PROJECT_ROLE_SITE_PI).exists()

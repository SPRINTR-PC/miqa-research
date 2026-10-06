"""`adopt_legacy_consent_participants` (#241): the legacy SamtyckenUmu task created Study
Participants without a project. The ETL `participant_consent` Datatype matches participants per
project, so before the first ETL consent import they are moved into the consent project
(MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME) -- only those with a consent of that project's types.
"""
from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    StudyParticipant,
)

CONSENT_PROJECT = "SamtyckenUmu"


@pytest.fixture(autouse=True)
def consent_project_setting(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='
    settings.TASK_CONSENT_RESEARCH_PROJECT_NAME = CONSENT_PROJECT


@pytest.fixture
def consent_project():
    return ResearchProject.objects.create(name=CONSENT_PROJECT, description="consent")


@pytest.fixture
def other_project():
    return ResearchProject.objects.create(name="Other", description="other")


def _participant(alias1: str, project: ResearchProject | None = None) -> StudyParticipant:
    return StudyParticipant.objects.create(
        alias1=alias1, person_source_value=f"psv-{alias1}", research_project=project)


def _consent(participant: StudyParticipant, project: ResearchProject) -> ParticipantConsent:
    consent_type, _ = ParticipantConsentType.objects.get_or_create(label="Delta i studien", research_project=project)
    clinic, _ = Clinic.objects.get_or_create(clinic_code="64001", defaults={"clinic_name": "64001"})
    return ParticipantConsent.objects.create(
        study_participant=participant, consent_type=consent_type, clinic=clinic,
        consent_signed_date=datetime(2026, 1, 1, tzinfo=UTC))


def _run(*args) -> str:
    out = StringIO()
    call_command("adopt_legacy_consent_participants", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_adopts_project_less_participants_with_a_consent_in_the_consent_project(consent_project, other_project):
    legacy = _participant("LEGACY")
    _consent(legacy, consent_project)
    no_consent = _participant("NO-CONSENT")
    other_consent = _participant("OTHER-CONSENT")
    _consent(other_consent, other_project)
    already_placed = _participant("PLACED", other_project)
    _consent(already_placed, consent_project)

    output = _run()

    for participant in (legacy, no_consent, other_consent, already_placed):
        participant.refresh_from_db()
    assert legacy.research_project == consent_project
    assert no_consent.research_project is None
    assert other_consent.research_project is None
    assert already_placed.research_project == other_project
    assert "Adopted 1 " in output


@pytest.mark.django_db
def test_counts_a_participant_with_several_consents_once(consent_project):
    legacy = _participant("LEGACY")
    _consent(legacy, consent_project)
    second_type = ParticipantConsentType.objects.create(label="Blodprov", research_project=consent_project)
    ParticipantConsent.objects.create(
        study_participant=legacy, consent_type=second_type, clinic=Clinic.objects.get(clinic_code="64001"),
        consent_signed_date=datetime(2026, 1, 1, tzinfo=UTC))

    output = _run()

    assert "Adopted 1 " in output


@pytest.mark.django_db
def test_is_idempotent(consent_project):
    legacy = _participant("LEGACY")
    _consent(legacy, consent_project)

    _run()
    output = _run()

    legacy.refresh_from_db()
    assert legacy.research_project == consent_project
    assert "Adopted 0 " in output


@pytest.mark.django_db
def test_dry_run_reports_without_changing_anything(consent_project):
    legacy = _participant("LEGACY")
    _consent(legacy, consent_project)

    output = _run("--dry-run")

    legacy.refresh_from_db()
    assert legacy.research_project is None
    assert "Would adopt 1 " in output


@pytest.mark.django_db
def test_fails_when_the_consent_project_setting_is_unset(settings):
    settings.TASK_CONSENT_RESEARCH_PROJECT_NAME = None

    with pytest.raises(CommandError, match="MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME"):
        _run()


@pytest.mark.django_db
def test_fails_when_the_consent_project_does_not_exist():
    with pytest.raises(CommandError, match=CONSENT_PROJECT):
        _run()


@pytest.mark.django_db
def test_skips_and_reports_a_legacy_participant_whose_person_is_already_in_the_consent_project(consent_project):
    legacy = StudyParticipant.objects.create(alias1="LEGACY", person_source_value="191212121212")
    _consent(legacy, consent_project)
    StudyParticipant.objects.create(
        alias1="ETL-CREATED", person_source_value="191212121212", research_project=consent_project)
    clean = _participant("CLEAN")
    _consent(clean, consent_project)

    output = _run()

    legacy.refresh_from_db()
    clean.refresh_from_db()
    assert legacy.research_project is None
    assert clean.research_project == consent_project
    assert "Adopted 1 " in output
    assert "LEGACY" in output and "ETL-CREATED" in output
    assert "191212121212" not in output  # never print the personnummer


@pytest.mark.django_db
def test_dry_run_also_reports_collisions(consent_project):
    legacy = StudyParticipant.objects.create(alias1="LEGACY", person_source_value="191212121212")
    _consent(legacy, consent_project)
    StudyParticipant.objects.create(
        alias1="ETL-CREATED", person_source_value="191212121212", research_project=consent_project)

    output = _run("--dry-run")

    assert "Would adopt 0 " in output
    assert "LEGACY" in output and "ETL-CREATED" in output

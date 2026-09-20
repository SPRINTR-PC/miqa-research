from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.db import transaction

from MiqaResearch.data.models import (
    Clinic,
    ConsentDailyActiveSummary,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.tasks.consent.update_consent_summary import rebuild_consent_daily_active_summary

pytestmark = pytest.mark.django_db(transaction=True)


def dt(day: int) -> datetime:
    return datetime(2026, 1, day, 12, tzinfo=UTC)


@pytest.fixture
def project():
    return ResearchProject.objects.create(name="P", description="d")


@pytest.fixture
def consent_type(project):
    return ParticipantConsentType.objects.create(label="T", research_project=project)


@pytest.fixture
def clinic():
    return Clinic.objects.create(clinic_code="C1", clinic_name="Clinic 1")


def make_participant(alias: str, project) -> StudyParticipant:
    return StudyParticipant.objects.create(alias1=alias, research_project=project)


def consent(participant, clinic, consent_type, signed: int, revoked: int | None = None):
    return ParticipantConsent.objects.create(
        study_participant=participant,
        clinic=clinic,
        consent_type=consent_type,
        consent_signed_date=dt(signed),
        consent_revoked_date=dt(revoked) if revoked else None,
    )


def summary(project) -> dict:
    return {
        (r.clinic.clinic_code, r.day.day): r.active_participant_count
        for r in ConsentDailyActiveSummary.objects.filter(research_project=project).select_related("clinic")
    }


def test_rebuild_counts_running_active_participants(project, consent_type, clinic):
    a, b = make_participant("a", project), make_participant("b", project)
    consent(a, clinic, consent_type, signed=1, revoked=5)
    consent(b, clinic, consent_type, signed=3)

    rebuild_consent_daily_active_summary.func(str(project.pk))

    assert summary(project) == {("C1", 1): 1, ("C1", 3): 2, ("C1", 5): 1}


def test_rebuild_same_day_revoke_wins_and_resign_reactivates(project, consent_type, clinic):
    a = make_participant("a", project)
    consent(a, clinic, consent_type, signed=1, revoked=1)
    consent(a, clinic, consent_type, signed=4)

    rebuild_consent_daily_active_summary.func(str(project.pk))

    assert summary(project) == {("C1", 1): 0, ("C1", 4): 1}


def test_rebuild_counts_participant_once_across_consent_types(project, consent_type, clinic):
    other_type = ParticipantConsentType.objects.create(label="T2", research_project=project)
    a = make_participant("a", project)
    consent(a, clinic, consent_type, signed=1)
    consent(a, clinic, other_type, signed=2)

    rebuild_consent_daily_active_summary.func(str(project.pk))

    assert summary(project) == {("C1", 1): 1, ("C1", 2): 1}


def test_rebuild_replaces_stale_rows_and_ignores_other_projects(project, consent_type, clinic):
    other = ResearchProject.objects.create(name="O", description="d")
    other_type = ParticipantConsentType.objects.create(label="OT", research_project=other)
    consent(make_participant("a", project), clinic, consent_type, signed=1)
    consent(make_participant("o", other), clinic, other_type, signed=2)
    ConsentDailyActiveSummary.objects.create(research_project=project, clinic=clinic, day=dt(9).date(),
                                             active_participant_count=99)

    rebuild_consent_daily_active_summary.func(str(project.pk))

    assert summary(project) == {("C1", 1): 1}
    assert ConsentDailyActiveSummary.objects.filter(research_project=other).count() == 0


def test_summary_is_rebuilt_after_insert_update_and_delete(project, consent_type, clinic):
    calls: list[str] = []
    with patch(
        "MiqaResearch.data.signals._enqueue_consent_summary_rebuild",
        side_effect=lambda project_id: calls.append(project_id),
    ):
        c = consent(make_participant("a", project), clinic, consent_type, signed=1)
        assert calls == [str(project.pk)]
        c.consent_revoked_date = dt(2)
        c.save()
        assert len(calls) == 2
        c.delete()
        assert len(calls) == 3


def test_many_saves_in_one_transaction_enqueue_once(project, consent_type, clinic):
    a = make_participant("a", project)
    calls: list[str] = []
    with patch(
        "MiqaResearch.data.signals._enqueue_consent_summary_rebuild",
        side_effect=lambda project_id: calls.append(project_id),
    ):
        with transaction.atomic():
            for day in (1, 2, 3):
                consent(a, clinic, consent_type, signed=day)
            assert calls == []
        assert calls == [str(project.pk)]

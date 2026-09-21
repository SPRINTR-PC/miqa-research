"""Tests for the pseudonymous StudyParticipant alias1 generator."""
import pytest

from helpers import study_participant_alias
from helpers.study_participant_alias import generate_study_participant_alias1
from MiqaResearch.data.models import StudyParticipant


@pytest.fixture(autouse=True)
def fernet_key(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="


def test_generate_study_participant_alias1_returns_fresh_alias(db):
    alias = generate_study_participant_alias1()
    assert isinstance(alias, str)
    assert len(alias) > 0
    assert not StudyParticipant.objects.filter(alias1=alias).exists()


def test_generate_study_participant_alias1_retries_on_collision(db, monkeypatch):
    StudyParticipant.objects.create(alias1="Abandoned Able Turkey")

    def fake_alias():
        return "Abandoned Able Turkey"

    monkeypatch.setattr(study_participant_alias, "_get_study_participant_alias1", fake_alias)
    with pytest.raises(Exception, match="Failed to generate unique study participant alias1"):
        generate_study_participant_alias1()


def test_generate_study_participant_alias1_eventually_finds_free_alias(db, monkeypatch):
    StudyParticipant.objects.create(alias1="Abandoned Able Turkey")
    sequence = iter(["Abandoned Able Turkey", "Abandoned Able Turkey", "Fresh New Dog"])
    monkeypatch.setattr(study_participant_alias, "_get_study_participant_alias1", lambda: next(sequence))
    assert generate_study_participant_alias1() == "Fresh New Dog"

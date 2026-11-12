"""Participant Key matching (ADR 0035, #415): which Study Participant a Study's identifiers resolve to."""
import pytest

from MiqaResearch.actions.participant_keys import (
    AmbiguousParticipantMatch,
    ParticipantKeyConflict,
    link_study_keys,
)
from MiqaResearch.data.models import ParticipantKey, ResearchProject, StudyParticipant


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Key project", description="d")


@pytest.fixture
def other_project(db):
    return ResearchProject.objects.create(name="Other project", description="d")


def _participant(project, alias, psv=None):
    return StudyParticipant.objects.create(alias1=alias, person_source_value=psv, research_project=project)


def _keys(project):
    return {(k.key_type, k.value): k.study_participant for k in ParticipantKey.objects.filter(project=project)}


# (name, participants {alias: psv}, instances, kwargs, expected participant alias or None)
MATRIX = [
    ("no match is unlinked", {"A1": None}, [{"PatientID": "ZZZ"}], {}, None),
    ("PatientID vs alias1", {"A1": None}, [{"PatientID": "A1"}], {}, "A1"),
    ("configured tag vs alias1", {"A1": None}, [{"PatientID": "x", "AccessionNumber": "A1"}],
     {"configured_tag": "AccessionNumber"}, "A1"),
    ("configured tag beats PatientID", {"A1": None, "A2": None},
     [{"PatientID": "A2", "AccessionNumber": "A1"}], {"configured_tag": "AccessionNumber"}, "A1"),
    ("PatientID vs person_source_value, dash-stripped", {"A1": "199001011234"}, [{"PatientID": "19900101-1234"}],
     {"match_person_source_value": True}, "A1"),
    ("person_source_value off by default", {"A1": "199001011234"}, [{"PatientID": "199001011234"}], {}, None),
    ("alias1 beats person_source_value", {"A1": None, "A2": "A1"}, [{"PatientID": "A1"}],
     {"match_person_source_value": True}, "A1"),
]


@pytest.mark.parametrize("name,participants,instances,kwargs,expected", MATRIX, ids=[m[0] for m in MATRIX])
def test_matching_steps(project, name, participants, instances, kwargs, expected):
    made = {alias: _participant(project, alias, psv) for alias, psv in participants.items()}
    key = link_study_keys(project, instances, **kwargs)
    assert key.study_participant == (made[expected] if expected else None)


def test_ambiguous_person_source_value_is_an_error(project):
    _participant(project, "A1", "111")
    _participant(project, "A2", "111")
    with pytest.raises(AmbiguousParticipantMatch):
        link_study_keys(project, [{"PatientID": "111"}], match_person_source_value=True)


def test_matching_is_project_scoped(project, other_project):
    _participant(other_project, "A1")
    assert link_study_keys(project, [{"PatientID": "A1"}]).study_participant is None


def test_study_key_is_first_configured_tag_present_else_patient_id(project):
    key = link_study_keys(project, [{"PatientID": " P1 ", "AccessionNumber": "ACC"}], configured_tag="AccessionNumber")
    assert (key.key_type, key.value) == ("dicom:AccessionNumber", "ACC")
    key = link_study_keys(project, [{"PatientID": " P1 "}], configured_tag="AccessionNumber")
    assert (key.key_type, key.value) == ("dicom:PatientID", "P1")


def test_same_identifier_reuses_the_key(project):
    first = link_study_keys(project, [{"PatientID": "P1"}])
    assert link_study_keys(project, [{"PatientID": "P1"}]).pk == first.pk
    assert ParticipantKey.objects.count() == 1


def test_key_value_is_case_preserved(project):
    link_study_keys(project, [{"PatientID": "p1"}])
    link_study_keys(project, [{"PatientID": "P1"}])
    assert ParticipantKey.objects.count() == 2


def test_link_all_observed_keys(project):
    participant = _participant(project, "A1")
    key = link_study_keys(
        project, [{"PatientID": "A1", "AccessionNumber": "ACC", "OtherPatientIDs": ["O1", "O2"]}]
    )
    assert key.study_participant == participant
    assert set(_keys(project)) == {
        ("dicom:PatientID", "A1"), ("dicom:AccessionNumber", "ACC"),
        ("dicom:OtherPatientIDs", "O1"), ("dicom:OtherPatientIDs", "O2"),
    }
    assert set(_keys(project).values()) == {participant}
    assert {k.linked_via for k in ParticipantKey.objects.all()} == {"match"}


def test_later_study_with_a_linked_key_resolves_through_it(project):
    participant = _participant(project, "A1")
    link_study_keys(project, [{"PatientID": "A1", "AccessionNumber": "ACC"}])
    key = link_study_keys(project, [{"PatientID": "unrelated", "AccessionNumber": "ACC"}])
    assert key.study_participant == participant
    assert _keys(project)[("dicom:AccessionNumber", "ACC")] == participant


def test_all_instances_of_a_study_resolve_to_one_participant(project):
    _participant(project, "A1")
    _participant(project, "A2")
    with pytest.raises(ParticipantKeyConflict):
        link_study_keys(project, [{"PatientID": "A1"}, {"PatientID": "A2"}])
    assert not ParticipantKey.objects.exists()


def test_cross_instance_conflict_when_one_instance_is_unmatched(project):
    _participant(project, "A1")
    with pytest.raises(ParticipantKeyConflict):
        link_study_keys(project, [{"PatientID": "A1"}, {"PatientID": "nope"}])


def test_conflicting_link_links_nothing(project):
    a1 = _participant(project, "A1")
    a2 = _participant(project, "A2")
    link_study_keys(project, [{"PatientID": "A1", "AccessionNumber": "ACC"}])
    before = _keys(project)
    with pytest.raises(ParticipantKeyConflict):
        # PatientID matches A2 but ACC is already linked to A1
        link_study_keys(project, [{"PatientID": "A2", "AccessionNumber": "ACC", "StudyID": "S1"}])
    assert _keys(project) == before
    assert a1 != a2


@pytest.mark.parametrize("tag", ["PatientSex", "PatientBirthDate", "Modality", ""])
def test_configured_tag_must_be_allow_listed(project, tag):
    with pytest.raises(ValueError):
        link_study_keys(project, [{"PatientID": "A1"}], configured_tag=tag)


def test_no_identifier_is_an_error(project):
    with pytest.raises(ValueError):
        link_study_keys(project, [{"PatientID": "  "}])


def test_never_creates_participants(project):
    link_study_keys(project, [{"PatientID": "P9"}])
    assert not StudyParticipant.objects.exists()

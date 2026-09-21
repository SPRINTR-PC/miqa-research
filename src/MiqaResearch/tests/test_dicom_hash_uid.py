"""
DICOM UID pseudonymization (CTP-style HashUID) per #118 / design #115:

- hash_uid: "2.25." root + SHA256-derived decimal digits (big-integer conversion),
  CTP leading-zero guard, 64-character UID cap
- get_or_create_hashuid_salt_key: per-ResearchProject salt, auto-generated once, never rotated
- pseudonymize_uid: deterministic per project, distinct across projects
"""
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from helpers.dicom_uid import get_or_create_hashuid_salt_key, hash_uid, pseudonymize_uid
from MiqaResearch.data.models import ResearchProject


def _assert_valid_pseudonym_shape(pseudonym: str) -> None:
    digits = pseudonym[len("2.25."):]
    assert pseudonym.startswith("2.25.")
    assert digits.isdecimal()
    assert not digits.startswith("0")
    assert len(pseudonym) <= 64


@pytest.fixture(autouse=True)
def fernet_key(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(
        name=f"HashUID project-{uuid4().hex[:8]}",
        description="Project for HashUID tests",
    )


@pytest.mark.parametrize(
    ("uid", "salt", "expected"),
    [
        (
            "1.2.826.0.1.3680043.8.498",
            "0123456789abcdef" * 4,
            "2.25.43099022001972006038279675551099159874812810425032790219153",
        ),
        (
            "1.3.6.1.4.1.25403.1.1.1",
            "deadbeef" * 8,
            "2.25.11003996731694297781897759663864455594203574273057541572335",
        ),
    ],
)
def test_hash_uid_matches_spec_worked_example(uid, salt, expected):
    assert hash_uid(uid, salt) == expected


@settings(max_examples=200)
@given(uid=st.text(min_size=1, max_size=128), salt=st.text(min_size=1, max_size=128))
def test_pseudonym_never_has_leading_zero_or_exceeds_uid_cap(uid, salt):
    _assert_valid_pseudonym_shape(hash_uid(uid, salt))


@settings(max_examples=200)
@given(
    uid=st.from_regex(r"1\.2\.[0-9]{1,10}\.[0-9]{1,10}", fullmatch=True),
    salt=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
)
def test_pseudonym_shape_holds_for_realistic_uids_and_salt_keys(uid, salt):
    _assert_valid_pseudonym_shape(hash_uid(uid, salt))


def test_hash_uid_is_deterministic_and_salt_dependent():
    uid, salt_a, salt_b = "1.2.840.113619.2.1", "a" * 64, "b" * 64
    assert hash_uid(uid, salt_a) == hash_uid(uid, salt_a)
    assert hash_uid(uid, salt_a) != hash_uid(uid, salt_b)


@pytest.mark.django_db
def test_salt_key_is_auto_generated_on_first_use_and_unchanged_after(research_project):
    assert research_project.dicom_hashuid_salt_key is None

    first_key = get_or_create_hashuid_salt_key(research_project)

    research_project.refresh_from_db()
    assert research_project.dicom_hashuid_salt_key == first_key

    assert get_or_create_hashuid_salt_key(research_project) == first_key
    assert get_or_create_hashuid_salt_key(research_project) == first_key


@pytest.mark.django_db
def test_pseudonymize_uid_is_deterministic_across_calls(research_project):
    uid = "1.2.840.113619.2.55.1"

    assert pseudonymize_uid(uid, research_project) == pseudonymize_uid(uid, research_project)


@pytest.mark.django_db
def test_pseudonymize_uid_auto_generates_project_salt(research_project):
    pseudonymize_uid("1.2.840.113619.2.55.1", research_project)

    research_project.refresh_from_db()
    assert research_project.dicom_hashuid_salt_key is not None


@pytest.mark.django_db
def test_pseudonymize_uid_differs_across_projects(db):
    project_a = ResearchProject.objects.create(name=f"HashUID project A-{uuid4().hex[:8]}", description="...")
    project_b = ResearchProject.objects.create(name=f"HashUID project B-{uuid4().hex[:8]}", description="...")
    uid = "1.2.840.113619.2.55.1"

    assert pseudonymize_uid(uid, project_a) != pseudonymize_uid(uid, project_b)

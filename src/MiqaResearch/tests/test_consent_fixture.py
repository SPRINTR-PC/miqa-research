"""Tests for the consent fixture data generator (MiqaResearch/data/fixtures/consent-data.py).

The fixture must follow the structure of
tests/example_data/participant_consent/consents_example.csv: 2000 rows,
signed dates spread over the last 15 months, 10 clinics, and all consents
linked to the single research project "SPRiNTR" (via the consent label
columns, which map to ParticipantConsentType -> ResearchProject in the
import pipeline).
"""
import csv
import importlib
import json
import re
import uuid as uuid_lib
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from django.core.management import call_command

from MiqaResearch.data.models import (
    Clinic,
    ParticipantConsent,
    ParticipantConsentType,
    ResearchProject,
    StudyParticipant,
)

consent_fixture = importlib.import_module("MiqaResearch.data.fixtures.consent-data")
RESEARCH_PROJECT_NAME = consent_fixture.RESEARCH_PROJECT_NAME
FIRST_LABEL = consent_fixture.FIRST_CONSENT_LABEL
FUTURE_LABEL = consent_fixture.FUTURE_RESEARCH_CONSENT_LABEL

EXPECTED_MODELS = {
    "data.researchproject",
    "data.participantconsenttype",
    "data.clinic",
    "data.studyparticipant",
    "data.participantconsent",
}
ORDERED_MODELS = (
    "data.researchproject",
    "data.participantconsenttype",
    "data.clinic",
    "data.studyparticipant",
    "data.participantconsent",
)

EXAMPLE_CSV = (
    Path(__file__).parent / "example_data" / "participant_consent" / "consents_example.csv"
)

STOCKHOLM = ZoneInfo("Europe/Stockholm")
FIXED_NOW = datetime(2026, 4, 20, 12, 0, tzinfo=STOCKHOLM)
FIXED_NOW_NAIVE = FIXED_NOW.replace(tzinfo=None)
PID_RE = re.compile(r"^\d{8}-\d{4}$")
STATUS_SIGNED = "Signerat"
STATUS_REVOKED = "Återtaget"


def example_csv_columns() -> list[str]:
    with open(EXAMPLE_CSV, newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    return consent_fixture.generate_consent_rows(now=FIXED_NOW, seed=42)


@pytest.fixture(scope="module")
def csv_text() -> str:
    return consent_fixture.generate_consent_csv(now=FIXED_NOW, seed=42)


def test_row_count_is_2000(rows):
    assert len(rows) == 2000
    assert consent_fixture.NUM_ROWS == 2000


def test_columns_match_example_csv_structure(rows):
    fixture_columns = list(rows[0].keys())
    # Logical (unquoted) form of the example CSV header
    expected = [col.replace('""', '"') for col in example_csv_columns()]
    assert fixture_columns == expected


def test_csv_header_roundtrips_like_example_csv(csv_text):
    # Read both through polars (same as the import pipeline) and compare
    # column names exactly, including the doubled-quote header quirk.
    fixture_df = pl.read_csv(StringIO(csv_text))
    example_df = pl.read_csv(EXAMPLE_CSV)
    assert fixture_df.columns == example_df.columns
    assert fixture_df.height == 2000


def test_clinics_are_exactly_10(rows):
    clinics = {row["klinik"] for row in rows}
    assert len(clinics) == 10
    assert len(consent_fixture.CLINICS) == 10
    assert clinics == set(consent_fixture.CLINICS)


def test_signed_dates_spread_over_last_15_months(rows):
    signed = [datetime.strptime(row["Signerat"], "%Y-%m-%d %H:%M") for row in rows]
    start = _subtract_months(FIXED_NOW_NAIVE, 15)
    assert all(start <= s <= FIXED_NOW_NAIVE for s in signed)
    # Spread: must not be bunched in one month — cover at least 14 distinct months
    months = {(s.year, s.month) for s in signed}
    assert len(months) >= 14
    assert (max(signed) - min(signed)).days >= 420


def test_all_consents_linked_to_sprintr_project(rows):
    assert consent_fixture.RESEARCH_PROJECT_NAME == "SPRiNTR"
    label_cols = [
        col for col in rows[0]
        if col not in ("Namn", "Personnummer", "Status", "Signerat",
                       "Senast Uppdaterad", "Återtaget", "klinik", "fpi", "Kommentar")
    ]
    # At least one consent label column references the SPRiNTR project
    # (example CSV spells the program all-caps as "SPRINTR-Real")
    assert any(RESEARCH_PROJECT_NAME.lower() in col.lower() for col in label_cols)
    for row in rows:
        for col in label_cols:
            assert row[col] in ("Ja", "Nej")


def test_status_and_retraction_consistency(rows):
    for row in rows:
        signed = datetime.strptime(row["Signerat"], "%Y-%m-%d %H:%M")
        if row["Status"] == STATUS_REVOKED:
            assert row["Återtaget"]
            revoked = datetime.strptime(row["Återtaget"], "%Y-%m-%d %H:%M")
            assert signed < revoked <= FIXED_NOW_NAIVE
        elif row["Status"] == STATUS_SIGNED:
            assert row["Återtaget"] == ""
        else:
            pytest.fail(f"unexpected status {row['Status']!r}")


def test_last_updated_not_before_signed_and_within_window(rows):
    for row in rows:
        signed = datetime.strptime(row["Signerat"], "%Y-%m-%d %H:%M")
        updated = datetime.strptime(row["Senast Uppdaterad"], "%Y-%m-%d %H:%M")
        assert signed <= updated <= FIXED_NOW_NAIVE


def test_personnummer_unique_and_well_formed(rows):
    pids = [row["Personnummer"] for row in rows]
    assert len(set(pids)) == 2000
    assert all(PID_RE.match(pid) for pid in pids)


def test_fpi_values_follow_example_convention(rows):
    assert {row["fpi"] for row in rows} <= {"3.0", "3.1", "3.2", "3.3"}


def test_csv_is_deterministic_for_fixed_now_and_seed():
    a = consent_fixture.generate_consent_csv(now=FIXED_NOW, seed=42)
    b = consent_fixture.generate_consent_csv(now=FIXED_NOW, seed=42)
    assert a == b
    c = consent_fixture.generate_consent_csv(now=FIXED_NOW, seed=43)
    assert c != a


@pytest.fixture(scope="module")
def fixture_objects() -> list[dict]:
    return json.loads(consent_fixture.generate_django_fixture(now=FIXED_NOW, seed=42))


def _objects_of(model: str, objects: list[dict]) -> list[dict]:
    return [obj for obj in objects if obj["model"] == model]


def _expected_consent_count(rows: list[dict[str, str]]) -> int:
    return sum(1 for row in rows if row[FIRST_LABEL] == "Ja") + \
        sum(1 for row in rows if row[FUTURE_LABEL] == "Ja")


def test_django_fixture_object_structure(fixture_objects):
    assert fixture_objects, "fixture must not be empty"
    for obj in fixture_objects:
        assert set(obj) == {"model", "pk", "fields"}
        assert obj["model"] in EXPECTED_MODELS
        uuid_lib.UUID(obj["pk"])  # valid UUID
        assert isinstance(obj["fields"], dict)
    # dependencies must be serialized before dependents
    first_seen = [obj["model"] for i, obj in enumerate(fixture_objects)
                  if obj["model"] not in {o["model"] for o in fixture_objects[:i]}]
    assert first_seen == list(ORDERED_MODELS)


def test_django_fixture_single_sprintr_project(fixture_objects):
    projects = _objects_of("data.researchproject", fixture_objects)
    assert len(projects) == 1
    assert projects[0]["fields"]["name"] == "SPRiNTR"


def test_django_fixture_10_clinics(fixture_objects):
    clinics = _objects_of("data.clinic", fixture_objects)
    assert len(clinics) == 10
    assert {c["fields"]["clinic_name"] for c in clinics} == set(consent_fixture.CLINICS)


def test_django_fixture_consent_types_linked_to_sprintr(fixture_objects):
    project_pk = _objects_of("data.researchproject", fixture_objects)[0]["pk"]
    types = _objects_of("data.participantconsenttype", fixture_objects)
    assert {t["fields"]["label"] for t in types} == {FIRST_LABEL, FUTURE_LABEL}
    assert all(t["fields"]["research_project"] == project_pk for t in types)


def test_django_fixture_2000_participants(rows, fixture_objects):
    project_pk = _objects_of("data.researchproject", fixture_objects)[0]["pk"]
    participants = _objects_of("data.studyparticipant", fixture_objects)
    assert len(participants) == 2000
    assert len({p["fields"]["alias1"] for p in participants}) == 2000
    assert {p["fields"]["person_source_value"] for p in participants} == \
        {row["Personnummer"] for row in rows}
    assert all(p["fields"]["research_project"] == project_pk for p in participants)
    for p in participants:
        pid = p["fields"]["person_source_value"]
        f = p["fields"]
        assert (f["year_of_birth"], f["month_of_birth"], f["day_of_birth"]) == \
            (int(pid[0:4]), int(pid[4:6]), int(pid[6:8]))
        assert f["gender"] == ("M" if int(pid[9]) % 2 == 1 else "F")


def test_django_fixture_consents(rows, fixture_objects):
    participant_pks = {p["pk"] for p in _objects_of("data.studyparticipant", fixture_objects)}
    type_pks = {t["pk"] for t in _objects_of("data.participantconsenttype", fixture_objects)}
    clinic_pks = {c["pk"] for c in _objects_of("data.clinic", fixture_objects)}
    consents = _objects_of("data.participantconsent", fixture_objects)
    assert len(consents) == _expected_consent_count(rows)
    start = _subtract_months(FIXED_NOW_NAIVE, 15)
    for c in consents:
        f = c["fields"]
        assert f["study_participant"] in participant_pks
        assert f["consent_type"] in type_pks
        assert f["clinic"] in clinic_pks
        signed = datetime.fromisoformat(f["consent_signed_date"])
        updated = datetime.fromisoformat(f["last_updated"])
        assert start <= signed.replace(tzinfo=None) <= FIXED_NOW_NAIVE
        assert signed.replace(tzinfo=None) <= updated.replace(tzinfo=None) \
            <= FIXED_NOW_NAIVE + timedelta(minutes=1)
        if f["status"] == STATUS_REVOKED:
            assert f["consent_revoked_date"] is not None
            assert signed < datetime.fromisoformat(f["consent_revoked_date"])
        else:
            assert f["status"] == STATUS_SIGNED
            assert f["consent_revoked_date"] is None


def test_write_django_fixture_writes_json_file(tmp_path, fixture_objects):
    out = tmp_path / "consent_data.json"
    written = consent_fixture.write_django_fixture(output_path=out, now=FIXED_NOW, seed=42)
    assert written == out
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == fixture_objects
    assert consent_fixture.FIXTURE_FILENAME == "consent_data.json"


@pytest.mark.django_db
def test_loaddata_loads_fixture_into_database(settings, tmp_path, rows):
    settings.DEBUG = True
    out = tmp_path / "consent_data.json"
    consent_fixture.write_django_fixture(output_path=out, now=FIXED_NOW, seed=42,
                                         hash_key=settings.SENSITIVE_DATA_HASH_KEY)

    call_command("loaddata", str(out), verbosity=0)

    expected_consents = _expected_consent_count(rows)
    assert ResearchProject.objects.filter(name="SPRiNTR").count() == 1
    assert Clinic.objects.count() == 10
    assert ParticipantConsentType.objects.count() == 2
    assert StudyParticipant.objects.count() == 2000
    # searchable-encrypted hash columns were provided (raw loaddata skips pre_save)
    assert StudyParticipant.objects.filter(person_source_value_hash__isnull=True).count() == 0
    assert ParticipantConsent.objects.count() == expected_consents
    # all consents link (via consent type) to the SPRiNTR research project
    assert ParticipantConsent.objects.filter(
        consent_type__research_project__name="SPRiNTR").count() == expected_consents

    first_row = rows[0]
    participant = StudyParticipant.objects.filter_by_person_source_value_list(
        [first_row["Personnummer"]]).first()
    assert participant is not None
    assert participant.name == first_row["Namn"]
    assert participant.research_project.name == "SPRiNTR"

    # signed dates survive loaddata with Europe/Stockholm semantics
    consents = list(ParticipantConsent.objects.filter(study_participant=participant))
    assert consents
    for consent in consents:
        assert consent.consent_signed_date.astimezone(STOCKHOLM).strftime("%Y-%m-%d %H:%M") \
            == first_row["Signerat"]
        assert consent.last_updated.astimezone(STOCKHOLM).strftime("%Y-%m-%d %H:%M") \
            == first_row["Senast Uppdaterad"]


def _subtract_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 - months
    year = dt.year + month // 12
    month = month % 12 + 1
    import calendar
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)

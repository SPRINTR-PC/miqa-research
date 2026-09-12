"""Fixture data for participant consents.

Generates 2000 consent rows following the structure of
tests/example_data/participant_consent/consents_example.csv (same column
headers, order, value conventions and CSV quoting style):

- signed dates (``Signerat``) uniformly spread over the last 15 months
- exactly 10 clinics
- all consents linked to the single research project ``SPRiNTR``: the
  consent label columns map to ``ParticipantConsentType`` records in the
  import pipeline (see MiqaResearch/actions/consents/participant_consents.py),
  and the primary label column references the SPRiNTR project by name.

The generator is deterministic for a fixed ``now`` and ``seed``. Dates are
rendered in naive Europe/Stockholm local time with ``%Y-%m-%d %H:%M``
format, matching the format parsed by MiqaResearch/tasks/participant_consent.py.

``generate_django_fixture()`` / ``write_django_fixture()`` additionally emit a
Django loaddata fixture (consent_data.json) with the same data as model
objects: ResearchProject "SPRiNTR", consent types, clinics, participants and
consents. Running the module directly (``python consent-data.py``) writes
consent_data.json next to this file.
"""
import calendar
import csv
import hashlib
import hmac
import json
import random
import uuid
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

RESEARCH_PROJECT_NAME = "SPRiNTR"
NUM_ROWS = 2000
SPREAD_MONTHS = 15
TIMEZONE = "Europe/Stockholm"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"

# 10 clinics, id-number style like the example CSV
CLINICS: tuple[str, ...] = (
    "64001", "55123", "77890", "99012", "45678",
    "55667", "60123", "44012", "33123", "22450",
)

# Consent label columns (non-standard CSV columns become consent labels in the
# import pipeline). The first references the SPRiNTR research project.
FIRST_CONSENT_LABEL = (
    f'Jag har läst och förstått "Information till forskningspersoner" '
    f"och samtycker till att delta i {RESEARCH_PROJECT_NAME.upper()}-Real"
)
FUTURE_RESEARCH_CONSENT_LABEL = (
    "Jag samtycker till att mina uppgifter och prover får sparas för framtida forskning"
)

# Column headers must match tests/example_data/participant_consent/consents_example.csv
NAME_COL = "Namn"
PID_COL = "Personnummer"
STATUS_COL = "Status"
SIGNED_COL = "Signerat"
LAST_UPDATED_COL = "Senast Uppdaterad"
RETRACTED_COL = "Återtaget"
CLINIC_COL = "klinik"
FPI_COL = "fpi"
COMMENT_COL = "Kommentar"

COLUMNS: tuple[str, ...] = (
    NAME_COL, PID_COL, STATUS_COL, SIGNED_COL, LAST_UPDATED_COL, RETRACTED_COL,
    CLINIC_COL, FPI_COL, FIRST_CONSENT_LABEL, FUTURE_RESEARCH_CONSENT_LABEL, COMMENT_COL,
)

STATUS_SIGNED = "Signerat"
STATUS_REVOKED = "Återtaget"
REVOCATION_RATE = 0.2
FPI_VERSIONS: tuple[str, ...] = ("3.0", "3.1", "3.2", "3.3")

_FIRST_NAMES = (
    "Anna", "Lars", "Maria", "Johan", "Karin", "Per", "Eva", "Daniel", "Sofia",
    "Anders", "Helena", "Fredrik", "Malin", "Oskar", "Lisa", "Peter", "Ida",
    "Mikael", "Bo", "Carl", "Britta", "Gunilla", "Stig", "Margareta", "Nils",
    "Ingrid", "Sven", "Åsa", "Tomas", "Agneta",
)
_LAST_NAMES = (
    "Karlsson", "Eriksson", "Andersson", "Svensson", "Nilsson", "Johansson",
    "Gustafsson", "Larsson", "Berg", "Lind", "Nyström", "Holm", "Olsson",
    "Petersson", "Lindberg", "Lindqvist", "Carlsson", "Sjöberg", "Magnusson",
    "Kjellberg", "Dahl", "Lundberg",
)
# Mostly empty; the rest are Swedish comments in the style of the example CSV.
_COMMENTS = (
    "", "", "", "", "", "", "", "",
    "Återkallade samtycke efter kontakt",
    "Vill inte delta i framtida studier",
    "Flyttade utomlands",
    "Kompletterade uppgifter",
    "Avbröt deltagande av personliga skäl",
    "Ej nöjd med informationen",
)

# Django loaddata fixture (MiqaResearch/data/fixtures/consent_data.json)
FIXTURE_FILENAME = "consent_data.json"
_MODEL_RESEARCH_PROJECT = "data.researchproject"
_MODEL_CONSENT_TYPE = "data.participantconsenttype"
_MODEL_CLINIC = "data.clinic"
_MODEL_PARTICIPANT = "data.studyparticipant"
_MODEL_CONSENT = "data.participantconsent"

# Alias pools, same "Adjective Adjective Animal" format as
# helpers/study_participant_alias.py (kept local so this module stays stdlib-only)
_ALIAS_ADJECTIVES = (
    "Able", "Amused", "Brave", "Calm", "Clever", "Curious", "Dapper", "Diligent",
    "Eager", "Fancy", "Gentle", "Glossy", "Handsome", "Humble", "Jolly", "Keen",
    "Lively", "Lucky", "Merry", "Modest", "Neat", "Patient", "Quick", "Radiant",
    "Rapid", "Steady", "Sunny", "Thoughtful", "Vivid", "Witty", "Zealous",
)
_ALIAS_ANIMALS = (
    "Badger", "Cat", "Deer", "Dog", "Duck", "Fox", "Goat", "Hare", "Hedgehog",
    "Kangaroo", "Koala", "Lion", "Lynx", "Moose", "Owl", "Otter", "Panda",
    "Pigeon", "Rabbit", "Reindeer", "Sheep", "Stag", "Walrus", "Wolf",
)


def _normalize_now(now: datetime | None) -> datetime:
    """Return naive Europe/Stockholm local time."""
    if now is None:
        now = datetime.now(ZoneInfo(TIMEZONE))
    if now.tzinfo is not None:
        now = now.astimezone(ZoneInfo(TIMEZONE))
    return now.replace(tzinfo=None)


def _subtract_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 - months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _truncate_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def _random_pid(rng: random.Random, used: set[str]) -> str:
    while True:
        birth_year = rng.randint(1945, 2005)
        birth_month = rng.randint(1, 12)
        birth_day = rng.randint(1, calendar.monthrange(birth_year, birth_month)[1])
        series = rng.randint(0, 9999)
        pid = f"{birth_year:04d}{birth_month:02d}{birth_day:02d}-{series:04d}"
        if pid not in used:
            used.add(pid)
            return pid


def generate_consent_rows(now: datetime | None = None, seed: int = 42) -> list[dict[str, str]]:
    """Generate NUM_ROWS consent rows as dicts keyed by COLUMNS.

    ``now`` anchors the 15-month window (default: current time in Europe/Stockholm).
    ``seed`` makes the output deterministic for a fixed ``now``.
    """
    now = _normalize_now(now)
    window_start = _subtract_months(now, SPREAD_MONTHS)
    span_seconds = (now - window_start).total_seconds()
    rng = random.Random(seed)
    used_pids: set[str] = set()

    rows: list[dict[str, str]] = []
    for _ in range(NUM_ROWS):
        signed = _truncate_to_minute(window_start + timedelta(seconds=rng.random() * span_seconds))

        revoked = None
        if rng.random() < REVOCATION_RATE:
            status = STATUS_REVOKED
            revoked = signed + timedelta(minutes=rng.randint(60 * 24, 60 * 24 * 21))
            if revoked > now:
                revoked = min(now, signed + (now - signed) // 2)
                if revoked <= signed:
                    revoked = now
        else:
            status = STATUS_SIGNED

        if revoked is not None:
            last_updated = revoked
        else:
            last_updated = signed + timedelta(minutes=rng.randint(1, 30)) if rng.random() < 0.1 else signed
            if last_updated > now:
                last_updated = now
            if last_updated < signed:
                last_updated = signed

        rows.append({
            NAME_COL: f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}",
            PID_COL: _random_pid(rng, used_pids),
            STATUS_COL: status,
            SIGNED_COL: signed.strftime(DATETIME_FORMAT),
            LAST_UPDATED_COL: last_updated.strftime(DATETIME_FORMAT),
            RETRACTED_COL: revoked.strftime(DATETIME_FORMAT) if revoked else "",
            CLINIC_COL: rng.choice(CLINICS),
            FPI_COL: rng.choice(FPI_VERSIONS),
            FIRST_CONSENT_LABEL: "Ja",
            FUTURE_RESEARCH_CONSENT_LABEL: "Ja" if rng.random() < 0.6 else "Nej",
            COMMENT_COL: rng.choice(_COMMENTS),
        })
    return rows


def generate_consent_csv(now: datetime | None = None, seed: int = 42) -> str:
    """Generate the fixture as a UTF-8 CSV string with the same quoting style
    as the example CSV (all fields quoted, embedded quotes doubled)."""
    buffer = StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in generate_consent_rows(now=now, seed=seed):
        writer.writerow([row[col] for col in COLUMNS])
    return buffer.getvalue()


def _fixture_uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _unique_alias(rng: random.Random, used: set[str]) -> str:
    while True:
        alias = f"{rng.choice(_ALIAS_ADJECTIVES)} {rng.choice(_ALIAS_ADJECTIVES)} {rng.choice(_ALIAS_ANIMALS)}"
        if alias not in used:
            used.add(alias)
            return alias


def _aware_iso(dt: datetime) -> str:
    """Serialize naive Europe/Stockholm local time as ISO 8601 with offset."""
    return dt.replace(tzinfo=ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")


def _deterministic_hash(value: str, key: str) -> str:
    """Same algorithm as helpers/db_fields.get_deterministic_hash (kept local so
    this module stays stdlib-only)."""
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_django_fixture(now: datetime | None = None, seed: int = 42,
                            hash_key: str | None = None) -> str:
    """Generate the consent fixture data as a Django loaddata JSON fixture.

    Contains, in dependency order: 1 ResearchProject ("SPRiNTR"), 2
    ParticipantConsentType records (the consent label columns, linked to the
    project), 10 Clinics, 2000 StudyParticipants (one per fixture row) and
    one ParticipantConsent per consented label per row — the same DB state the
    import pipeline would produce from the CSV form of this fixture.

    ``hash_key`` (optional): the SENSITIVE_DATA_HASH_KEY to use for the
    searchable-encrypted hash columns. loaddata saves with raw=True, which
    skips pre_save, so without an explicit hash the pid/name search columns
    would end up NULL. Pass the key of the environment the fixture is loaded
    in; omit it to leave those columns unset.
    """
    rows = generate_consent_rows(now=now, seed=seed)
    rng = random.Random(seed)
    objects: list[dict] = []

    def add(model: str, pk: str, fields: dict) -> None:
        objects.append({"model": model, "pk": pk, "fields": fields})

    project_pk = _fixture_uuid(rng)
    add(_MODEL_RESEARCH_PROJECT, project_pk, {
        "name": RESEARCH_PROJECT_NAME,
        "description": f"Research project for the {RESEARCH_PROJECT_NAME} consent fixture data.",
    })

    type_pks: dict[str, str] = {}
    for label in (FIRST_CONSENT_LABEL, FUTURE_RESEARCH_CONSENT_LABEL):
        type_pk = _fixture_uuid(rng)
        add(_MODEL_CONSENT_TYPE, type_pk, {
            "label": label,
            "description": "",
            "research_project": project_pk,
        })
        type_pks[label] = type_pk

    clinic_pks: dict[str, str] = {}
    for clinic in CLINICS:
        clinic_pk = _fixture_uuid(rng)
        add(_MODEL_CLINIC, clinic_pk, {"clinic_name": clinic})
        clinic_pks[clinic] = clinic_pk

    participant_pks: dict[str, str] = {}
    used_aliases: set[str] = set()
    for row in rows:
        pid = row[PID_COL]
        participant_pk = _fixture_uuid(rng)
        participant_fields = {
            "person_source_value": pid,
            "name": row[NAME_COL],
            "alias1": _unique_alias(rng, used_aliases),
            "gender": "M" if int(pid[9]) % 2 == 1 else "F",
            "year_of_birth": int(pid[0:4]),
            "month_of_birth": int(pid[4:6]),
            "day_of_birth": int(pid[6:8]),
            "research_project": project_pk,
        }
        if hash_key is not None:
            participant_fields["person_source_value_hash"] = _deterministic_hash(pid, hash_key)
            participant_fields["name_hash"] = _deterministic_hash(row[NAME_COL], hash_key)
        add(_MODEL_PARTICIPANT, participant_pk, participant_fields)
        participant_pks[pid] = participant_pk

    for row in rows:
        for label in (FIRST_CONSENT_LABEL, FUTURE_RESEARCH_CONSENT_LABEL):
            if row[label] != "Ja":
                continue
            revoked = (
                _aware_iso(datetime.strptime(row[RETRACTED_COL], DATETIME_FORMAT))
                if row[RETRACTED_COL] else None
            )
            add(_MODEL_CONSENT, _fixture_uuid(rng), {
                "study_participant": participant_pks[row[PID_COL]],
                "status": row[STATUS_COL],
                "consent_signed_date": _aware_iso(datetime.strptime(row[SIGNED_COL], DATETIME_FORMAT)),
                # loaddata saves with raw=True (skips pre_save), so the auto_now
                # field must be provided explicitly
                "last_updated": _aware_iso(datetime.strptime(row[LAST_UPDATED_COL], DATETIME_FORMAT)),
                "consent_revoked_date": revoked,
                "clinic": clinic_pks[row[CLINIC_COL]],
                "consent_type": type_pks[label],
            })

    return json.dumps(objects, indent=1, ensure_ascii=False)


def write_django_fixture(output_path: Path | str | None = None, now: datetime | None = None,
                         seed: int = 42, hash_key: str | None = None) -> Path:
    """Write the Django fixture JSON to ``output_path`` (default:
    consent_data.json next to this module). Returns the written path."""
    path = Path(output_path) if output_path is not None else Path(__file__).resolve().parent / FIXTURE_FILENAME
    path.write_text(generate_django_fixture(now=now, seed=seed, hash_key=hash_key), encoding="utf-8")
    return path


if __name__ == "__main__":
    written_path = write_django_fixture()
    print(f"Wrote Django fixture to {written_path}")


def main():
    csv_data = generate_consent_csv()
    with open("consent_fixture.csv", "w", encoding="utf-8") as f:
        f.write(csv_data)


if __name__ == "__main__":
    main()

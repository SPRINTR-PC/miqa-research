"""Native (built-in) ETL Scripts (#226): global, read-only Scripts shipped with the codebase.

Each entry's source file lives next to this module, optionally with a `<stem>.schema.json` sidecar:
the JSON Schema its Bindings' config must satisfy (#238). It must be self-contained -- stdlib plus the
curated `etl-python` uv group (#413), no MiqaResearch or mires_etl imports -- since it runs in the sandbox as `script.py`, and a project's Customize
copy of it has to keep working on its own. `sync_native_etl_scripts` (run on every migrate)
mirrors this list into EtlScript/EtlScriptVersion rows.
"""
from dataclasses import dataclass
from pathlib import Path

NATIVE_SCRIPTS_DIR = Path(__file__).parent


@dataclass(frozen=True)
class NativeScript:
    name: str
    datatype_name: str
    filename: str
    description: str


NATIVE_SCRIPTS: tuple[NativeScript, ...] = (
    NativeScript(
        name="CSV → participant consent",
        datatype_name="participant_consent",
        filename="csv_participant_consent.py",
        description=(
            "Reads consent CSV exports (by default the SamtyckenUmu format) and produces one "
            "participant_consent row per consent marked as given. Config keys, all optional, are "
            "offered as fields from its config schema."
        ),
    ),
    NativeScript(
        name="CSV → participant key link",
        datatype_name="participant_key_link",
        filename="csv_participant_key_link.py",
        description=(
            "Reads a mapping CSV and produces one participant_key_link row per line: a key (by default "
            "a DICOM PatientID pseudonym) and the Study Participant it belongs to, by alias1 or "
            "person_source_value. Config: key type, delimiter, encoding, column names, fill_demographics."
        ),
    ),
    NativeScript(
        name="DICOM files → dicom_instance",
        datatype_name="dicom_instance",
        filename="dicom_instance.py",
        description=(
            "Reads DICOM headers (never pixels) and produces one dicom_instance row per input file: "
            "raw UIDs, geometry, identifier tags and a per-SOP-class payload. Non-DICOM files, "
            "DICOMDIR and directory records are skipped; files missing UIDs fail the Job."
        ),
    ),
)


def native_script_path(filename: str) -> Path:
    return NATIVE_SCRIPTS_DIR / filename

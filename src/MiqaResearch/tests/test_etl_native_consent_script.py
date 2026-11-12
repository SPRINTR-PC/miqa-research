"""The native "CSV → participant consent" ETL Script (#226), run through the Python shim's
`run_script` exactly as the sandbox runs it. Its defaults match the SamtyckenUmu consent export
the legacy consent task reads (Swedish column names, "Ja" for a given consent, Europe/Stockholm
local times), and a Binding's config can override any of them.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from MiqaResearch.etl_native_scripts import native_script_path
from mires_etl import contract
from mires_etl.shim import read_result_jsonl, run_script

HEADER = "Namn,Personnummer,Status,Signerat,Senast Uppdaterad,Återtaget,klinik,Kommentar,Blodprov,Bilder\n"


@pytest.fixture
def script_main():
    spec = importlib.util.spec_from_file_location(
        "csv_participant_consent", native_script_path("csv_participant_consent.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _run(tmp_path: Path, script_main, csv_text: str, config: dict | None = None):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "export.csv").write_text(csv_text, encoding="utf-8")
    output_dir = tmp_path / "output"
    result = run_script(
        main=script_main, manifest={"datatype": "participant_consent", "config": config or {}},
        input_dir=input_dir, output_dir=output_dir)
    rows = []
    if result.succeeded:
        rows = [json.loads(line) for line in read_result_jsonl(output_dir / contract.RESULT_FILENAME)
                .rows_jsonl.splitlines()]
    return result, rows


def test_a_samtycken_umu_export_becomes_one_consent_row_per_consented_label(tmp_path, script_main):
    csv_text = HEADER + "Tolvan Tolvansson,19121212-1212,Signerad,2026-03-01 10:00:00,2026-03-02 10:00,,K-01,,Ja,Nej\n"

    result, rows = _run(tmp_path, script_main, csv_text)

    assert result.exit_code == contract.EXIT_SUCCESS, result.log
    assert rows == [{
        "person_source_value": "191212121212",
        "name": "Tolvan Tolvansson",
        "consent_type": "Blodprov",
        "consent_signed_date": "2026-03-01T10:00:00+01:00",
        "status": "Signerad",
        "consent_revoked_date": None,
        "clinic_code": "K-01",
        "participant_information_version": None,
        "source": None,
    }]


def test_a_csv_missing_a_required_column_fails_naming_the_column(tmp_path, script_main):
    csv_text = "Namn,Personnummer,Status,Signerat,Blodprov\nTolvan,19121212-1212,Signerad,2026-03-01 10:00,Ja\n"

    result, _ = _run(tmp_path, script_main, csv_text)

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert "export.csv is missing required column(s): klinik" in result.log


def test_a_bindings_config_can_describe_a_differently_shaped_export(tmp_path, script_main):
    csv_text = (
        "ssn;full_name;signed_at;revoked_at;site;notes;Imaging\n"
        "19121212-1212;Tolvan;2026-01-15 08:30;2026-02-01 12:00:00;S-9;x;yes\n"
        "19900101-1234;Other;2026-01-16 08:30;;S-9;;no\n"
    )
    config = {
        "delimiter": ";",
        "consented_values": ["yes"],
        "source": "Lab export",
        "columns": {
            "person_source_value": "ssn", "name": "full_name", "signed": "signed_at", "revoked": "revoked_at",
            "clinic": "site", "ignore": ["notes"],
        },
    }

    result, rows = _run(tmp_path, script_main, csv_text, config)

    assert result.exit_code == contract.EXIT_SUCCESS, result.log
    assert [(row["person_source_value"], row["consent_type"]) for row in rows] == [("191212121212", "Imaging")]
    assert rows[0]["consent_signed_date"] == "2026-01-15T08:30:00+01:00"
    assert rows[0]["consent_revoked_date"] == "2026-02-01T12:00:00+01:00"
    assert rows[0]["clinic_code"] == "S-9"
    assert rows[0]["source"] == "Lab export"

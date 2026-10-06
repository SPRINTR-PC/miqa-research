"""`sync_native_etl_scripts` (#226): mirrors the codebase's native ETL Scripts
(`MiqaResearch.etl_native_scripts.NATIVE_SCRIPTS`) into global, read-only EtlScript rows, each with
immutable Versions. Idempotent; a changed source publishes a new Version (Bindings keep the one
they pinned); a native Script dropped from the codebase is archived, never deleted.
"""
import hashlib
import json

import pytest
from django.core.management import call_command

from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch import etl_native_scripts
from MiqaResearch.data.models import EtlScript, EtlScriptVersion
from MiqaResearch.etl_config_schema import ConfigSchema, parse_config_schema
from MiqaResearch.etl_native_scripts import NativeScript


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def native_dir(tmp_path, monkeypatch):
    """A stand-in native-scripts directory, so tests can change and remove sources."""
    directory = tmp_path / "native"
    directory.mkdir()
    (directory / "consent.py").write_bytes(b"def main(ctx):\n    return iter(())\n")
    monkeypatch.setattr(etl_native_scripts, "NATIVE_SCRIPTS_DIR", directory)
    monkeypatch.setattr(etl_native_scripts, "NATIVE_SCRIPTS", (
        NativeScript(name="Consent import", datatype_name="participant_consent", filename="consent.py",
                     description="Imports consents."),
    ))
    return directory


@pytest.mark.django_db
def test_sync_creates_each_native_script_with_an_immutable_first_version(native_dir, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}

    call_command("sync_native_etl_scripts")

    script = EtlScript.objects.get(origin=ETL_SCRIPT_ORIGIN_NATIVE)
    assert (script.name, script.datatype_name, script.project_id) == ("Consent import", "participant_consent", None)
    assert script.description == "Imports consents."
    version = EtlScriptVersion.objects.get(script=script)
    assert version.version == 1
    assert version.image_key == "python-etl-v1"
    assert version.sha256 == hashlib.sha256(b"def main(ctx):\n    return iter(())\n").hexdigest()
    assert version.source.read() == b"def main(ctx):\n    return iter(())\n"


@pytest.mark.django_db
def test_syncing_again_without_changes_publishes_no_new_version(native_dir):
    call_command("sync_native_etl_scripts")
    call_command("sync_native_etl_scripts")

    assert EtlScript.objects.filter(origin=ETL_SCRIPT_ORIGIN_NATIVE).count() == 1
    assert EtlScriptVersion.objects.count() == 1


@pytest.mark.django_db
def test_a_changed_source_publishes_a_new_version_and_keeps_the_old_one(native_dir):
    call_command("sync_native_etl_scripts")
    first = EtlScriptVersion.objects.get()
    (native_dir / "consent.py").write_bytes(b"def main(ctx):\n    yield from ()\n")

    call_command("sync_native_etl_scripts")

    versions = list(EtlScriptVersion.objects.order_by("version").values_list("id", "version"))
    assert versions == [(first.id, 1), (versions[1][0], 2)]
    assert EtlScriptVersion.objects.get(version=2).sha256 == hashlib.sha256(
        b"def main(ctx):\n    yield from ()\n").hexdigest()


@pytest.mark.django_db
def test_a_native_script_dropped_from_the_codebase_is_archived_not_deleted(native_dir, monkeypatch):
    call_command("sync_native_etl_scripts")
    monkeypatch.setattr(etl_native_scripts, "NATIVE_SCRIPTS", ())

    call_command("sync_native_etl_scripts")

    script = EtlScript.objects.get(origin=ETL_SCRIPT_ORIGIN_NATIVE)
    assert script.archived_at is not None
    assert script.versions.count() == 1


DELIMITER_SCHEMA = {"type": "object", "properties": {"delimiter": {"type": "string"}}}


@pytest.mark.django_db
def test_a_native_scripts_sidecar_schema_becomes_its_versions_config_schema(native_dir):
    (native_dir / "consent.schema.json").write_text(json.dumps(DELIMITER_SCHEMA))

    call_command("sync_native_etl_scripts")

    assert EtlScriptVersion.objects.get().config_schema == DELIMITER_SCHEMA


@pytest.mark.django_db
def test_a_native_script_without_a_sidecar_schema_has_no_config_schema(native_dir):
    call_command("sync_native_etl_scripts")

    assert EtlScriptVersion.objects.get().config_schema is None


@pytest.mark.django_db
def test_a_changed_sidecar_schema_alone_publishes_a_new_version(native_dir):
    call_command("sync_native_etl_scripts")
    (native_dir / "consent.schema.json").write_text(json.dumps(DELIMITER_SCHEMA))

    call_command("sync_native_etl_scripts")
    call_command("sync_native_etl_scripts")

    assert list(EtlScriptVersion.objects.order_by("version").values_list("version", "config_schema")) == [
        (1, None), (2, DELIMITER_SCHEMA)]


@pytest.mark.django_db
def test_a_malformed_sidecar_schema_is_logged_and_publishes_no_version_without_failing_the_sync(
        native_dir, monkeypatch, caplog):
    (native_dir / "consent.schema.json").write_text('{"type": "no-such-type"}')
    (native_dir / "other.py").write_bytes(b"def main(ctx):\n    return iter(())\n")
    monkeypatch.setattr(etl_native_scripts, "NATIVE_SCRIPTS", (
        *etl_native_scripts.NATIVE_SCRIPTS,
        NativeScript(name="Other", datatype_name="measurement", filename="other.py", description=""),
    ))

    call_command("sync_native_etl_scripts")

    assert list(EtlScriptVersion.objects.values_list("script__name", flat=True)) == ["Other"]
    assert "consent.schema.json" in caplog.text


def test_every_shipped_sidecar_schema_is_a_valid_config_schema():
    sidecars = sorted(etl_native_scripts.NATIVE_SCRIPTS_DIR.glob("*.schema.json"))

    assert sidecars
    for sidecar in sidecars:
        parse_config_schema(sidecar.read_bytes())


@pytest.mark.django_db
def test_the_shipped_consent_script_declares_a_config_schema_accepting_its_documented_defaults():
    call_command("sync_native_etl_scripts")

    version = EtlScriptVersion.objects.get(script__name="CSV → participant consent")
    documented_defaults = {
        "delimiter": ",", "encoding": "utf-8-sig", "timezone": "Europe/Stockholm", "consented_values": ["Ja"],
        "source": None, "columns": {
            "person_source_value": "Personnummer", "name": "Namn", "status": "Status", "signed": "Signerat",
            "revoked": "Återtaget", "clinic": "klinik",
            "participant_information_version": "participant_information_version",
            "ignore": ["Senast Uppdaterad", "Kommentar"]},
    }
    schema = ConfigSchema(version.config_schema)
    assert schema.errors(documented_defaults) == []
    assert schema.errors({}) == []
    assert schema.errors({"delimeter": ";"}) != []

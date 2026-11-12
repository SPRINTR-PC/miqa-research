"""`mires_etl` is Django-free (#412) and its schema and the app's loader registries stay in step."""
import subprocess
import sys

import pytest

from MiqaResearch.etl_datatypes.registry import loader_names
from mires_etl.schemas import ParticipantReferenceFields, get_schema, schema_names


def test_importing_mires_etl_pulls_in_no_django_or_celery():
    code = (
        "import sys, mires_etl, mires_etl.shim, mires_etl.r_shim, mires_etl.schemas\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('django', 'celery', 'ninja', 'MiqaResearch')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_every_schema_has_a_loader_and_every_loader_a_schema():
    assert set(schema_names()) == loader_names()


def test_existing_datatypes_validate_via_mires_etl_schemas():
    assert {"measurement", "visit_occurrence", "participant_consent"} <= set(schema_names())
    assert issubclass(get_schema("measurement"), ParticipantReferenceFields)
    with pytest.raises(ValueError):
        get_schema("measurement").model_validate({})


def test_entrypoint_copies_the_image_package_manifest_into_the_output(tmp_path, monkeypatch):
    from mires_etl.__main__ import copy_image_manifest

    manifest = tmp_path / "packages.txt"
    manifest.write_text("pydicom==3.0.2\n")
    monkeypatch.setenv("MIRES_ETL_PACKAGES_FILE", str(manifest))
    output = tmp_path / "root" / "output"

    copy_image_manifest(output)

    assert (output / "packages.txt").read_text() == "pydicom==3.0.2\n"


def test_entrypoint_skips_the_manifest_when_the_image_has_none(tmp_path, monkeypatch):
    from mires_etl.__main__ import copy_image_manifest

    monkeypatch.setenv("MIRES_ETL_PACKAGES_FILE", str(tmp_path / "missing.txt"))

    copy_image_manifest(tmp_path / "output")

    assert not (tmp_path / "output" / "packages.txt").exists()

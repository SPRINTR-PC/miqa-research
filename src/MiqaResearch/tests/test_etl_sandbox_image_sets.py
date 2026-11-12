"""Curated sandbox package sets (#413): the uv groups in pyproject.toml are the single source of truth for
what a Native Script may import (beyond the stdlib), the sandbox images copy no app code, and the baked
manifest lists the set."""
import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

from MiqaResearch.etl_native_scripts import NATIVE_SCRIPTS, native_script_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _group_requirement_names(group: str) -> set[str]:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    return {re.split(r"[<>=!~\[ ]", requirement, maxsplit=1)[0].lower()
            for requirement in pyproject["dependency-groups"][group]}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_etl_python_group_is_the_documented_curated_set():
    assert _group_requirement_names("etl-python") == {"pydicom", "polars", "numpy"}
    assert _group_requirement_names("etl-shim") == {"pydantic"}


@pytest.mark.parametrize("script", NATIVE_SCRIPTS, ids=lambda script: script.filename)
def test_native_script_imports_only_stdlib_and_the_etl_python_set(script):
    # Every distribution in the group imports under its own name.
    allowed = set(sys.stdlib_module_names) | _group_requirement_names("etl-python")

    imported = _imported_top_level_modules(native_script_path(script.filename))

    assert imported <= allowed, f"{script.filename} imports outside stdlib + etl-python: {imported - allowed}"


def test_python_sandbox_image_copies_only_mires_etl_and_the_curated_groups():
    dockerfile = (PROJECT_ROOT / "etl_sandbox.Dockerfile").read_text()
    copies = re.findall(r"^COPY\s+(?!--from)(.+)$", dockerfile, flags=re.MULTILINE)

    assert "mires_etl ./mires_etl" in copies
    assert not any(re.match(r"\.\s+\.", copy) for copy in copies), "must not copy the whole app"
    assert "--only-group etl-python" in dockerfile and "--only-group etl-shim" in dockerfile
    assert "DJANGO_SETTINGS_MODULE" not in dockerfile
    assert "/etc/mires/packages.txt" in dockerfile


def test_r_sandbox_image_installs_the_curated_r_set_and_extends_the_manifest():
    dockerfile = (PROJECT_ROOT / "etl_sandbox_r.Dockerfile").read_text()

    for package in ("jsonlite", "dplyr", "readr", "tidyr", "lubridate"):
        assert f"r-cran-{package}" in dockerfile
    assert ">> /etc/mires/packages.txt" in dockerfile

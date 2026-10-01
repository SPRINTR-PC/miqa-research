"""Real Sphinx builds of the manuals via documentation/build_manuals.py (marker: manuals)."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.manuals

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_DIR / "documentation" / "build_manuals.py"


def run_build(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_builds_english_json_for_every_manual(tmp_path):
    result = run_build("--build-dir", tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "user" / "en" / "index.fjson").is_file()
    assert (tmp_path / "technical" / "en" / "index.fjson").is_file()


@pytest.fixture
def manuals_dir(tmp_path):
    """A writable copy of the real manual sources."""
    copy = tmp_path / "manuals"
    shutil.copytree(PROJECT_DIR / "documentation" / "manuals", copy)
    return copy


def test_sphinx_warning_fails_build_unless_no_strict(tmp_path, manuals_dir):
    with (manuals_dir / "user" / "index.md").open("a") as f:
        f.write("\nSee {ref}`no-such-label`.\n")

    strict = run_build("--manuals-dir", manuals_dir, "--build-dir", tmp_path / "strict")
    lenient = run_build("--manuals-dir", manuals_dir, "--build-dir", tmp_path / "lenient", "--no-strict")

    assert strict.returncode != 0
    assert lenient.returncode == 0, lenient.stderr
    assert (tmp_path / "lenient" / "user" / "en" / "index.fjson").is_file()


def test_locale_directory_adds_a_language_build_for_that_manual_only(tmp_path, manuals_dir):
    (manuals_dir / "user" / "locale" / "sv" / "LC_MESSAGES").mkdir(parents=True)

    result = run_build("--manuals-dir", manuals_dir, "--build-dir", tmp_path / "builds")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "builds" / "user" / "sv" / "index.fjson").is_file()
    assert (tmp_path / "builds" / "user" / "en" / "index.fjson").is_file()
    assert sorted(p.name for p in (tmp_path / "builds" / "technical").iterdir()) == ["en"]

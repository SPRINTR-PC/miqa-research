"""Real Sphinx builds of the manuals via documentation/build_manuals.py (marker: manuals)."""

import json
import os
import re
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
    """A writable copy of the real manual sources, without their translations (locale/)."""
    copy = tmp_path / "manuals"
    shutil.copytree(PROJECT_DIR / "documentation" / "manuals", copy, ignore=shutil.ignore_patterns("locale"))
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


def test_writes_a_search_index_with_one_entry_per_section(tmp_path):
    result = run_build("--build-dir", tmp_path)

    assert result.returncode == 0, result.stderr
    for manual in ("user", "technical"):
        entries = json.loads((tmp_path / manual / "en" / "search.json").read_text(encoding="utf-8"))
        assert entries
        assert all(set(entry) == {"page", "anchor", "title", "breadcrumb", "text"} for entry in entries)
        assert not any(entry["page"] in {"search", "genindex"} for entry in entries)

    user = json.loads((tmp_path / "user" / "en" / "search.json").read_text(encoding="utf-8"))
    native = next(entry for entry in user if entry["title"] == "Native scripts")
    assert native["page"] == "src/etl-pipelines"
    assert native["anchor"] == "native-scripts"
    assert native["breadcrumb"] == ["ETL Pipelines", "Creating a custom script"]
    assert "¶" not in native["text"] and "<" not in native["text"]


def test_writes_labels_json_from_sphinx_labels(tmp_path):
    result = run_build("--build-dir", tmp_path)

    assert result.returncode == 0, result.stderr
    labels = json.loads((tmp_path / "user" / "en" / "labels.json").read_text(encoding="utf-8"))
    assert labels["heading-etl-pipelines-native"] == {
        "page": "src/etl-pipelines",
        "anchor": "heading-etl-pipelines-native",
        "title": "Native scripts",
    }
    assert all(set(target) == {"page", "anchor", "title"} for target in labels.values())
    assert (tmp_path / "technical" / "en" / "labels.json").is_file()


# {% manual_link "user" "app-…" %} in templates; manual_url(request, "user", "app-…") in code.
HELP_LINK_PATTERNS = [
    re.compile(r"""\{%\s*manual_link\s+["'](?P<manual>[\w-]+)["']\s+["'](?P<label>[\w-]+)["']"""),
    re.compile(r"""manual_url\(\s*\w+\s*,\s*["'](?P<manual>[\w-]+)["']\s*,\s*["'](?P<label>[\w-]+)["']"""),
]
SKIPPED_DIRS = {"tests", "node_modules", "LocalOnly", "documentation", "static"}


def help_links_in_app():
    """Every (manual, label) a template or Python module links to."""
    found = set()
    for root, dirs, files in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if d not in SKIPPED_DIRS and not d.startswith(".")]
        for name in files:
            if name.endswith((".html", ".py")):
                text = (Path(root) / name).read_text(encoding="utf-8", errors="ignore")
                found |= {(m["manual"], m["label"]) for regex in HELP_LINK_PATTERNS for m in regex.finditer(text)}
    return found


def test_every_help_link_label_exists_in_the_english_build(tmp_path):
    result = run_build("--build-dir", tmp_path)
    assert result.returncode == 0, result.stderr

    links = help_links_in_app()
    assert ("user", "app-dashboard-overview") in links
    missing = [
        (manual, label)
        for manual, label in sorted(links)
        if label not in json.loads((tmp_path / manual / "en" / "labels.json").read_text(encoding="utf-8"))
    ]
    assert missing == []


FIXTURE_BUILD_DIR = PROJECT_DIR / "tests" / "fixtures" / "manuals"
# Sphinx's own pages, never served by the app (search.fjson is not search.json).
SPHINX_ONLY_PAGES = {"search.fjson", "genindex.fjson"}


def _served(paths):
    return [path for path in paths if path.name not in SPHINX_ONLY_PAGES and ".doctrees" not in path.parts]


def _keys(paths, entries_of):
    return {
        key for path in paths for entry in entries_of(json.loads(path.read_text(encoding="utf-8"))) for key in entry
    }


def test_real_output_has_every_key_the_fixtures_rely_on(tmp_path):
    """Drift guard: the hand-written fixture build must not use keys a real build lacks."""
    result = run_build("--build-dir", tmp_path)
    assert result.returncode == 0, result.stderr

    kinds = {
        "*.fjson": lambda page: [page],
        "search.json": lambda entries: entries,
        "labels.json": lambda labels: labels.values(),
    }
    for pattern, entries_of in kinds.items():
        fixture_keys = _keys(_served(FIXTURE_BUILD_DIR.rglob(pattern)), entries_of)
        assert fixture_keys, pattern
        real_files = _served(tmp_path.glob(f"*/*/**/{pattern}"))
        assert real_files, pattern
        for real in real_files:
            missing = fixture_keys - _keys([real], entries_of)
            assert not missing, f"{real.relative_to(tmp_path)} lacks {sorted(missing)}"

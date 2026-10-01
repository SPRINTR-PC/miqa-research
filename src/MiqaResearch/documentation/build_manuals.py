"""Build every manual into JSON (.fjson) for the in-app manual views.

Plain script, no Django: finds each ``manuals/<manual>/conf.py`` and builds English
plus every ``locale/<lang>/`` into ``<build-dir>/<manual>/<lang>/``.

    uv run --group docs python documentation/build_manuals.py [--build-dir DIR] [--no-strict] [--watch]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

DOCUMENTATION_DIR = Path(__file__).resolve().parent
DEFAULT_MANUALS_DIR = DOCUMENTATION_DIR / "manuals"
DEFAULT_BUILD_DIR = DOCUMENTATION_DIR / "builds"
SOURCE_LANGUAGE = "en"


def find_manuals(manuals_dir: Path) -> list[Path]:
    return sorted(conf.parent for conf in manuals_dir.glob("*/conf.py"))


def languages(manual_dir: Path) -> list[str]:
    locale_dir = manual_dir / "locale"
    translated = sorted(p.name for p in locale_dir.iterdir() if p.is_dir()) if locale_dir.is_dir() else []
    return [SOURCE_LANGUAGE, *(lang for lang in translated if lang != SOURCE_LANGUAGE)]


def build_manual(manual_dir: Path, build_dir: Path, strict: bool) -> bool:
    ok = True
    for lang in languages(manual_dir):
        out_dir = build_dir / manual_dir.name / lang
        doctree_dir = build_dir / ".doctrees" / manual_dir.name / lang
        cmd = [sys.executable, "-m", "sphinx", "-b", "json", "-D", f"language={lang}", "-d", str(doctree_dir)]
        if strict:
            cmd += ["-W", "--keep-going"]
        print(f"Building {manual_dir.name} [{lang}] -> {out_dir}", flush=True)
        ok &= subprocess.run([*cmd, str(manual_dir), str(out_dir)]).returncode == 0
    return ok


def build_all(manuals_dir: Path, build_dir: Path, strict: bool) -> bool:
    results = [build_manual(manual, build_dir, strict) for manual in find_manuals(manuals_dir)]
    return all(results)


def watch(manuals_dir: Path, build_dir: Path, strict: bool) -> None:
    from watchfiles import watch as watch_changes

    def is_source(_change, path: str) -> bool:
        return not path.endswith((".mo", "~")) and "/.doctrees/" not in path

    print(f"Watching {manuals_dir} for changes…", flush=True)
    for changes in watch_changes(manuals_dir, watch_filter=is_source):
        changed = {Path(path).relative_to(manuals_dir).parts[0] for _, path in changes}
        manuals = find_manuals(manuals_dir)
        # A change outside any manual (e.g. conf_common.py) affects them all.
        if not changed <= {m.name for m in manuals}:
            targets = manuals
        else:
            targets = [m for m in manuals if m.name in changed]
        for manual in targets:
            build_manual(manual, build_dir, strict)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=Path(os.environ.get("MANUALS_BUILD_DIR", DEFAULT_BUILD_DIR)),
        help="output root (env MANUALS_BUILD_DIR, default documentation/builds)",
    )
    parser.add_argument("--manuals-dir", type=Path, default=DEFAULT_MANUALS_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--no-strict", dest="strict", action="store_false", help="don't fail on Sphinx warnings")
    parser.add_argument("--watch", action="store_true", help="rebuild the affected manual on change")
    args = parser.parse_args(argv)

    manuals_dir = args.manuals_dir.resolve()
    build_dir = args.build_dir.resolve()
    ok = build_all(manuals_dir, build_dir, args.strict)
    if args.watch:
        watch(manuals_dir, build_dir, args.strict)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

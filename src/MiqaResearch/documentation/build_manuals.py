"""Build every manual into JSON (.fjson) for the in-app manual views.

Plain script, no Django: finds each ``manuals/<manual>/conf.py`` and builds English
plus every ``locale/<lang>/`` into ``<build-dir>/<manual>/<lang>/``, then writes that
build's section index for in-app search (``search.json``).

    uv run --group docs python documentation/build_manuals.py [--build-dir DIR] [--no-strict] [--watch]
"""

import argparse
import json
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

DOCUMENTATION_DIR = Path(__file__).resolve().parent
DEFAULT_MANUALS_DIR = DOCUMENTATION_DIR / "manuals"
DEFAULT_BUILD_DIR = DOCUMENTATION_DIR / "builds"
SOURCE_LANGUAGE = "en"
# Sphinx's own pages; the app never serves them, so they aren't searchable.
UNSEARCHED_PAGES = {"search", "genindex"}


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
        if out_dir.is_dir():
            write_search_index(out_dir)
    return ok


class _SectionParser(HTMLParser):
    """Splits a Sphinx page body into its ``<section id>``s: anchor, heading title, ancestry and own text."""

    INLINE_TAGS = {"a", "abbr", "b", "code", "em", "i", "kbd", "mark", "span", "strong", "sub", "sup"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []  # finished, in document order
        self.stack = []  # open sections
        self.skip = None  # [tag, depth] of an element whose text is left out
        self.in_heading = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if self.skip:
            self.skip[1] += tag == self.skip[0]
            return
        if tag in {"script", "style"} or "headerlink" in classes or (tag == "pre" and "mermaid" in classes):
            self.skip = [tag, 1]
        elif tag == "section" and attrs.get("id"):
            section = {"anchor": attrs["id"], "title": [], "text": [], "ancestors": [s["title"] for s in self.stack]}
            self.stack.append(section)
            self.sections.append(section)
        elif tag in self.HEADINGS and self.stack and not self.stack[-1]["title"]:
            self.in_heading = True
        elif tag not in self.INLINE_TAGS:
            self._text(" ")

    def handle_endtag(self, tag):
        if self.skip:
            self.skip[1] -= tag == self.skip[0]
            if self.skip[1] == 0:
                self.skip = None
        elif tag == "section" and self.stack:
            self.stack.pop()
        elif tag in self.HEADINGS:
            self.in_heading = False
        elif tag not in self.INLINE_TAGS:
            self._text(" ")

    def handle_data(self, data):
        if not self.skip:
            self._text(data)

    def _text(self, data):
        if self.stack:
            self.stack[-1]["title" if self.in_heading else "text"].append(data)


def _plain(parts) -> str:
    return " ".join("".join(parts).split())


def page_sections(page: dict) -> list[dict]:
    """One search entry per section of a built page (an ``.fjson`` dict)."""
    parser = _SectionParser()
    parser.feed(page["body"])
    parser.close()
    parents = [_plain([_strip_tags(parent["title"])]) for parent in page["parents"]]
    return [
        {
            "page": page["current_page_name"],
            "anchor": section["anchor"],
            "title": _plain(section["title"]),
            "breadcrumb": parents + [_plain(title) for title in section["ancestors"]],
            "text": _plain(section["text"]),
        }
        for section in parser.sections
    ]


def _strip_tags(html: str) -> str:
    parser = HTMLParser()
    parts = []
    parser.handle_data = parts.append
    parser.feed(html)
    parser.close()
    return "".join(parts)


def write_search_index(out_dir: Path) -> None:
    entries = []
    for path in sorted(out_dir.rglob("*.fjson")):
        page = json.loads(path.read_text(encoding="utf-8"))
        if page.get("current_page_name") not in UNSEARCHED_PAGES:
            entries += page_sections(page)
    (out_dir / "search.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


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

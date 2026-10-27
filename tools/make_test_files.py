#!/usr/bin/env python3
"""Create a directory tree of files with nonsense content, for testing uploads and Archive Rules.

Directory and file names are random words or fake person names. File names get a suffix picked from SUFFIXES
(plus any the user adds), and the content is random bytes or random text matching the suffix.

Usage: tools/make_test_files.py OUTPUT_DIR [--depth 3] [--suffix .xyz ...] [--seed 1] ...
       tools/make_test_files.py --help

Defaults live in the SETTINGS block below; command-line options override them.
"""
import argparse
import random
import sys
from pathlib import Path

# ---- SETTINGS: edit these, or override on the command line -------------------------------------------------------

DEPTH = 3                 # levels of directories below the output directory; files are made at every level
DIRS_PER_DIR = (1, 3)     # (min, max) subdirectories in each directory above the deepest level
FILES_PER_DIR = (2, 6)    # (min, max) files in each directory
FILE_SIZE = (64, 4096)    # (min, max) bytes of content per file

# The suffixes files get. Add your own here, or with --suffix on the command line.
SUFFIXES = [".txt", ".csv", ".json", ".log", ".dcm", ".ndpi", ".tif", ".jpg", ".png", ".xml", ".pdf", ".zip"]

# Suffixes whose content is random text lines instead of random bytes.
TEXT_SUFFIXES = {".txt", ".csv", ".json", ".log", ".xml"}

# ---- Name material -----------------------------------------------------------------------------------------------

WORDS = [
    "amber", "anchor", "aurora", "basalt", "beacon", "birch", "bramble", "cobalt", "comet", "copper", "coral", "cricket",
    "delta", "dune", "ember", "falcon", "fennel", "fjord", "garnet", "glacier", "harbor", "heron", "indigo", "juniper",
    "kelp", "lantern", "lichen", "lotus", "marble", "meadow", "mosaic", "nebula", "nectar", "obsidian", "olive", "onyx",
    "orchid", "pebble", "pine", "quartz", "raven", "reef", "saffron", "sparrow", "tundra", "umber", "velvet", "willow",
    "yarrow", "zephyr",
]
FIRST_NAMES = [
    "Alva", "Birger", "Cecilia", "Dagny", "Elof", "Freja", "Gunnar", "Hedda", "Ivar", "Jonna", "Knut", "Linnea", "Mats",
    "Nora", "Olle", "Petra", "Rurik", "Saga", "Tore", "Ulla", "Viggo", "Wilma", "Yngve", "Astrid",
]
LAST_NAMES = [
    "Andersson", "Bergstrom", "Carlsson", "Dahl", "Eklund", "Forsberg", "Granath", "Holm", "Isaksson", "Jansson",
    "Karlsson", "Lindqvist", "Nyberg", "Olsson", "Persson", "Sandberg", "Tornqvist", "Wallin",
]

# ------------------------------------------------------------------------------------------------------------------


def normalise_suffix(suffix: str) -> str:
    suffix = suffix.strip().lower()
    if not suffix or suffix == ".":
        raise ValueError("a suffix cannot be empty")
    if any(c in suffix for c in "/\\ "):
        raise ValueError(f"'{suffix}' is not a valid suffix")
    return suffix if suffix.startswith(".") else "." + suffix


def random_name(rng: random.Random) -> str:
    """A random word, two words, or a fake person name, as a filename-safe string."""
    kind = rng.choice(["word", "word", "pair", "person"])
    if kind == "word":
        return rng.choice(WORDS)
    if kind == "pair":
        return f"{rng.choice(WORDS)}-{rng.choice(WORDS)}"
    return f"{rng.choice(FIRST_NAMES)}_{rng.choice(LAST_NAMES)}"


def unique_name(rng: random.Random, taken: set[str], suffix: str = "") -> str:
    """A name not in `taken` (compared case-insensitively, so it also works on case-insensitive file systems)."""
    for _ in range(50):
        name = random_name(rng) + suffix
        if name.lower() not in taken:
            taken.add(name.lower())
            return name
    while True:  # the word lists are small: fall back to adding a number
        name = f"{random_name(rng)}-{rng.randrange(1000, 10000)}{suffix}"
        if name.lower() not in taken:
            taken.add(name.lower())
            return name


def random_content(rng: random.Random, suffix: str, size: int) -> bytes:
    if suffix in TEXT_SUFFIXES:
        text = bytearray()
        while len(text) < size:
            line = " ".join(rng.choice(WORDS) for _ in range(rng.randint(3, 10)))
            if suffix == ".csv":
                line = ",".join(line.split(" ")) + f",{rng.randint(0, 9999)}"
            text += (line + "\n").encode()
        return bytes(text[:size])
    return rng.randbytes(size)


def build_tree(root: Path, depth: int, suffixes: list[str], rng: random.Random) -> tuple[int, int, int]:
    """Fill `root` and returns (directories, files, bytes) created."""
    counts = [0, 0, 0]

    def fill(directory: Path, level: int) -> None:
        taken = {entry.name.lower() for entry in directory.iterdir()}
        for _ in range(rng.randint(*FILES_PER_DIR)):
            suffix = rng.choice(suffixes)
            data = random_content(rng, suffix, rng.randint(*FILE_SIZE))
            (directory / unique_name(rng, taken, suffix)).write_bytes(data)
            counts[1] += 1
            counts[2] += len(data)
        if level >= depth:
            return
        for _ in range(rng.randint(*DIRS_PER_DIR)):
            child = directory / unique_name(rng, taken)
            child.mkdir()
            counts[0] += 1
            fill(child, level + 1)

    root.mkdir(parents=True, exist_ok=True)
    fill(root, 0)
    return counts[0], counts[1], counts[2]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a tree of files with nonsense content.")
    parser.add_argument("output", type=Path, help="directory to fill (created if missing)")
    parser.add_argument("--depth", type=int, default=DEPTH, help=f"directory levels below OUTPUT (default {DEPTH})")
    parser.add_argument("--suffix", action="append", default=[], metavar="SUFFIX",
                        help="add a file suffix to the set, e.g. --suffix .svs (repeatable)")
    parser.add_argument("--only-suffixes", action="store_true",
                        help="use only the suffixes given with --suffix instead of adding to the built-in set")
    parser.add_argument("--seed", type=int, help="seed for the random generator, for a repeatable tree")
    parser.add_argument("--force", action="store_true", help="allow filling a directory that already has content")
    args = parser.parse_args(argv)

    if args.depth < 0:
        parser.error("--depth must not be negative")
    try:
        extra = [normalise_suffix(s) for s in args.suffix]
        base = [] if args.only_suffixes else [normalise_suffix(s) for s in SUFFIXES]
    except ValueError as error:
        parser.error(str(error))
    suffixes = list(dict.fromkeys(base + extra))
    if not suffixes:
        parser.error("no suffixes: give at least one with --suffix")

    if args.output.exists() and not args.output.is_dir():
        parser.error(f"{args.output} exists and is not a directory")
    if args.output.is_dir() and any(args.output.iterdir()) and not args.force:
        parser.error(f"{args.output} is not empty; use --force to add files to it")

    rng = random.Random(args.seed)
    directories, files, size = build_tree(args.output, args.depth, suffixes, rng)
    print(f"Created {files} files ({size:,} bytes) in {directories} directories under {args.output.resolve()}")
    print("Suffixes: " + " ".join(suffixes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""The ETL sandbox R shim (#166), Python side. An R Script runs in two halves inside the R
sandbox image:

1. `shim.R` (child process): reads `manifest.json` + `input/`, sources `script.R`, calls its
   `main(ctx)`, and appends each `emit(row)` as a JSON line to an intermediate rows file. Exits 0
   when `main` returned, 1 when the script's own code raised, 2 when `script.R` doesn't parse or
   defines no `main` -- the same meanings as `contract.py`'s exit codes. Its stdout/stderr is the
   run's log.
2. This module: launches that child, then feeds the emitted rows through the Python shim's own
   `run_script`, so R rows are validated against the very same Datatype schema, and `result.jsonl`
   is written with the very same all-or-nothing rule, as a Python Script's.

Keeping validation on the Python side means the ETL Datatype registry (#159) stays the one schema
source of truth -- nothing is re-expressed in R.
"""
import json
import subprocess
from io import StringIO
from pathlib import Path

from . import contract
from .shim import ShimResult, _contract_violation, _failed_run, run_script

SHIM_R_PATH = Path(__file__).with_name("shim.R")
ROWS_FILENAME = "emitted_rows.jsonl"

_CHILD_EXIT_CODES = (contract.EXIT_SUCCESS, contract.EXIT_SCRIPT_ERROR, contract.EXIT_CONTRACT_VIOLATION)


def run_r_sandbox(root: Path, *, command: list[str] | None = None) -> ShimResult:
    """The R image's file-based entrypoint -- `run_sandbox`'s counterpart. `command` replaces
    `Rscript shim.R` (tests stand a small program in for it); it's called with `<root> <rows file>`
    appended."""
    output_dir = root / contract.OUTPUT_DIRNAME
    try:
        manifest = json.loads((root / contract.MANIFEST_FILENAME).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return _contract_violation(output_dir, f"Could not read {contract.MANIFEST_FILENAME}: {exc}")

    rows_path = root / ROWS_FILENAME
    command = command or ["Rscript", "--vanilla", str(SHIM_R_PATH)]
    try:
        child = subprocess.run(
            [*command, str(root), str(rows_path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        child_log = child.stdout.decode(errors="replace")
        if child.returncode != contract.EXIT_SUCCESS:
            # Anything outside the child protocol (e.g. R itself crashing) is still the script's
            # run failing, never a contract violation the platform should be blamed for.
            exit_code = child.returncode if child.returncode in _CHILD_EXIT_CODES else contract.EXIT_SCRIPT_ERROR
            return _failed_run(
                exit_code, output_dir, StringIO(child_log), StringIO(),
                error=f"{contract.R_SCRIPT_FILENAME} run exited with status {child.returncode}.")

        return run_script(
            main=lambda ctx: _read_emitted_rows(rows_path), manifest=manifest,
            input_dir=root / contract.INPUT_DIRNAME, output_dir=output_dir, preamble=child_log)
    finally:
        rows_path.unlink(missing_ok=True)


def _read_emitted_rows(rows_path: Path):
    with rows_path.open() as rows_file:
        for line in rows_file:
            if line.strip():
                yield json.loads(line)

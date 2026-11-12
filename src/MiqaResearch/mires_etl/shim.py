"""The ETL sandbox Python shim (#160): the platform entrypoint baked into every Python sandbox
image, standing between the sandboxed container and a Script author's own code. See `contract.py`
for the fixed file layout and exit codes this module implements.
"""
import importlib.util
import json
import traceback
from collections.abc import Callable, Iterable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from pydantic import ValidationError

from . import contract
from .context import ScriptContext
from .schemas import SchemaNotRegistered, get_schema

ScriptMain = Callable[[ScriptContext], Iterable[dict]]


@dataclass(frozen=True)
class ShimResult:
    exit_code: int
    log: str = ""
    rows_written: int = 0
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.exit_code == contract.EXIT_SUCCESS


@dataclass(frozen=True)
class ResultDocument:
    """A parsed `result.jsonl`: the header's Datatype name, plus the row lines on their own --
    exactly the `jsonl_text` ticket 03's `load_jsonl` (#159) expects.
    """
    datatype: str
    rows_jsonl: str


def run_script(
        *, main: ScriptMain, manifest: dict, input_dir: Path, output_dir: Path, preamble: str = "") -> ShimResult:
    """Run an already-loaded script's `main(ctx)` against `manifest` + `input_dir`, writing
    `result.jsonl` and a log under `output_dir`. This is the contract's mid-level seam: it takes
    the script's `main` directly, so it can be exercised without a real sandbox or a script file
    on disk. `run_sandbox` below is the full, file-based entrypoint built on top of it.

    `preamble` carries any stdout/stderr already captured before `main` existed to be called (e.g.
    `run_sandbox`'s own module-loading phase, below) so it still lands in the one log this run
    writes, rather than being dropped.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    datatype_name = manifest.get("datatype")
    if not datatype_name:
        return _contract_violation(output_dir, 'manifest.json is missing a "datatype" field.')
    try:
        schema = get_schema(datatype_name)
    except SchemaNotRegistered as exc:
        return _contract_violation(output_dir, str(exc))

    ctx = ScriptContext(input_dir=input_dir, datatype=datatype_name, config=manifest.get("config", {}))
    stdout, stderr = StringIO(), StringIO()
    tmp_result_path = output_dir / f"{contract.RESULT_FILENAME}.tmp"
    rows_written = 0
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rows = main(ctx)
            with tmp_result_path.open("w") as result_file:
                result_file.write(json.dumps({"datatype": datatype_name}) + "\n")
                for row in rows:
                    validated = schema.model_validate(row)
                    result_file.write(validated.model_dump_json() + "\n")
                    rows_written += 1
    except ValidationError as exc:
        tmp_result_path.unlink(missing_ok=True)
        return _failed_run(
            contract.EXIT_CONTRACT_VIOLATION, output_dir, stdout, stderr, error=str(exc), preamble=preamble)
    except Exception as exc:
        tmp_result_path.unlink(missing_ok=True)
        return _failed_run(
            contract.EXIT_SCRIPT_ERROR, output_dir, stdout, stderr, error=str(exc),
            extra=traceback.format_exc(), preamble=preamble)

    # Only made visible once the whole run succeeded -- a downstream reader must never see a
    # partially written result.jsonl (contract.py).
    tmp_result_path.replace(output_dir / contract.RESULT_FILENAME)
    log = _write_log(output_dir, preamble + stdout.getvalue() + stderr.getvalue())
    return ShimResult(exit_code=contract.EXIT_SUCCESS, log=log, rows_written=rows_written)


def run_sandbox(root: Path) -> ShimResult:
    """The full, file-based entrypoint: load `manifest.json` and `script.py` from `root`, then
    hand off to `run_script`. This is what a container's actual entrypoint calls.
    """
    output_dir = root / contract.OUTPUT_DIRNAME
    try:
        manifest = json.loads((root / contract.MANIFEST_FILENAME).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return _contract_violation(output_dir, f"Could not read {contract.MANIFEST_FILENAME}: {exc}")

    # Loading the script file runs its module-level code, which is exactly as capable of raising
    # or printing as `main(ctx)` itself -- so it gets the same stdout/stderr capture and the same
    # "never leave the run unaccounted for" handling, not just a bare, uncaught import.
    stdout, stderr = StringIO(), StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            main = _load_script_main(root / contract.SCRIPT_FILENAME)
    except SyntaxError as exc:
        return _failed_run(
            contract.EXIT_CONTRACT_VIOLATION, output_dir, stdout, stderr,
            error=f"{contract.SCRIPT_FILENAME} is not valid Python: {exc}")
    except Exception as exc:
        return _failed_run(
            contract.EXIT_SCRIPT_ERROR, output_dir, stdout, stderr, error=str(exc), extra=traceback.format_exc())

    if main is None:
        return _failed_run(
            contract.EXIT_CONTRACT_VIOLATION, output_dir, stdout, stderr,
            error=f"{contract.SCRIPT_FILENAME} does not define a callable `main`.")

    return run_script(
        main=main, manifest=manifest, input_dir=root / contract.INPUT_DIRNAME, output_dir=output_dir,
        preamble=stdout.getvalue() + stderr.getvalue())


def read_result_jsonl(path: Path) -> ResultDocument:
    # split on "\n" only: str.splitlines also splits on U+0085/U+2028/U+2029, which JSON strings may contain raw
    header_line, _, rows_jsonl = path.read_text().partition("\n")
    header = json.loads(header_line)
    return ResultDocument(datatype=header["datatype"], rows_jsonl=rows_jsonl)


def _load_script_main(script_path: Path) -> ScriptMain | None:
    spec = importlib.util.spec_from_file_location("etl_sandbox_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = getattr(module, "main", None)
    return main if callable(main) else None


def _contract_violation(output_dir: Path, message: str) -> ShimResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    log = _write_log(output_dir, message + "\n")
    return ShimResult(exit_code=contract.EXIT_CONTRACT_VIOLATION, log=log, error=message)


def _failed_run(
        exit_code: int, output_dir: Path, stdout: StringIO, stderr: StringIO, *, error: str, extra: str = "",
        preamble: str = "") -> ShimResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    log = _write_log(output_dir, preamble + stdout.getvalue() + stderr.getvalue() + extra)
    return ShimResult(exit_code=exit_code, log=log, error=error)


def _write_log(output_dir: Path, text: str) -> str:
    (output_dir / contract.LOG_FILENAME).write_text(text)
    return text

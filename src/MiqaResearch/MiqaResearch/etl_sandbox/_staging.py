"""Input/output staging logic shared by every `SandboxBackend` (#161, #165): the input-size gate, the
`/sandbox` tar layout (`manifest.json`, `script.py`/`script.R`, `input/*`), and output-archive parsing. Kept
backend-agnostic (no Docker or Kubernetes import) so both backends enforce identical limits and read the
same contract -- neither gets a separate, looser path.
"""
import io
import json
import tarfile

from mires_etl import contract

from .exceptions import SandboxInputTooLarge
from .spec import SandboxRunSpec


def check_input_size(spec: SandboxRunSpec) -> None:
    total = len(spec.script_source) + sum(len(content) for content in spec.input_files.values())
    if total > spec.limits.max_input_bytes:
        raise SandboxInputTooLarge(
            f"Run {spec.run_id}'s staged input is {total} bytes, over the {spec.limits.max_input_bytes} byte cap.")


def build_sandbox_archive(spec: SandboxRunSpec) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_bytes(tar, contract.MANIFEST_FILENAME, json.dumps(spec.manifest).encode())
        _add_bytes(tar, contract.script_filename(spec.image_key), spec.script_source)
        for relative_path, content in spec.input_files.items():
            _add_bytes(tar, f"{contract.INPUT_DIRNAME}/{relative_path}", content)
    return buf.getvalue()


def _add_bytes(tar: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))


def read_output_from_tar(tar_bytes: bytes) -> tuple[bytes | None, bytes, str]:
    """Parse a tar archive of `output/` (as produced by `tar -c -C /sandbox output` or Docker's
    `get_archive`) into `(result_jsonl, log, image_manifest)`. Caller enforces `max_output_bytes` on the raw bytes
    *before* calling this -- it never inspects size itself.
    """
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r") as tar:
        result_jsonl = _read_member(tar, f"{contract.OUTPUT_DIRNAME}/{contract.RESULT_FILENAME}")
        log = _read_member(tar, f"{contract.OUTPUT_DIRNAME}/{contract.LOG_FILENAME}") or b""
        manifest = _read_member(tar, f"{contract.OUTPUT_DIRNAME}/{contract.PACKAGES_FILENAME}") or b""
    return result_jsonl, log, manifest.decode("utf-8", errors="replace")


def _read_member(tar: tarfile.TarFile, name: str) -> bytes | None:
    try:
        member = tar.getmember(name)
    except KeyError:
        return None
    extracted = tar.extractfile(member)
    return extracted.read() if extracted else None

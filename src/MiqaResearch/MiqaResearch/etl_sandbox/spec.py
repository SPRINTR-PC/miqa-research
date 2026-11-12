"""The `SandboxBackend.run()` request/response shapes (#161). Deliberately plain -- no Django
model reference -- so a backend (real or fake) is exercisable without a database, matching the
existing shim's own `manifest: dict, input_dir: Path` seam (`etl_shim/shim.py`). The orchestrator
(#162) is what builds a `SandboxRunSpec` from a `PipelineBinding` + `EtlJob` + `EtlScriptVersion`.
"""
from dataclasses import dataclass, field
from collections.abc import Sequence
from pathlib import Path

from .limits import SandboxLimits


@dataclass(frozen=True)
class StagedInput:
    """One input already fetched to the worker's scratch volume (#414): its path under the sandbox's
    `input/`, its size in bytes, and where the bytes live locally. The tar is built from the local file."""
    relative_path: str
    size: int
    local_path: Path


@dataclass(frozen=True)
class SandboxRunSpec:
    run_id: str
    image_key: str
    manifest: dict
    script_source: bytes
    limits: SandboxLimits
    input_files: Sequence[StagedInput] = field(default_factory=tuple)
    # Where the archive temp file is written (the same scratch volume as the inputs); None = system temp.
    scratch_dir: Path | None = None


@dataclass(frozen=True)
class SandboxRunResult:
    exit_code: int
    result_jsonl: bytes | None = None
    log: bytes = b""
    killed: bool = False

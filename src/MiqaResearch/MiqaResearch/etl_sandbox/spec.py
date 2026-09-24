"""The `SandboxBackend.run()` request/response shapes (#161). Deliberately plain -- no Django
model reference -- so a backend (real or fake) is exercisable without a database, matching the
existing shim's own `manifest: dict, input_dir: Path` seam (`etl_shim/shim.py`). The orchestrator
(#162) is what builds a `SandboxRunSpec` from a `PipelineBinding` + `EtlJob` + `EtlScriptVersion`.
"""
from dataclasses import dataclass, field

from .limits import SandboxLimits


@dataclass(frozen=True)
class SandboxRunSpec:
    run_id: str
    image_key: str
    manifest: dict
    script_source: bytes
    limits: SandboxLimits
    input_files: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxRunResult:
    exit_code: int
    result_jsonl: bytes | None = None
    log: bytes = b""
    killed: bool = False

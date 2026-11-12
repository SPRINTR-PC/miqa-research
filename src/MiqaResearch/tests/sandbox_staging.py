"""Test helper: stage `{relative_path: bytes}` as `StagedInput`s on disk (#414)."""
from pathlib import Path

from MiqaResearch.etl_sandbox import StagedInput


def stage_inputs(directory: Path, files: dict[str, bytes]) -> list[StagedInput]:
    staged = []
    for relative_path, content in files.items():
        path = directory / "staged" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        staged.append(StagedInput(relative_path=relative_path, size=len(content), local_path=path))
    return staged

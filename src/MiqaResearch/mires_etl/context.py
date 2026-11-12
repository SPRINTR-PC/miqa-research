from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScriptContext:
    """What a Script author's `main(ctx)` sees: the staged input and its own config. No database
    or network access is exposed here -- the sandbox has neither (#146) -- so a Script only ever
    reads files and yields rows; Participant Reference resolution happens later, at load time.
    """
    input_dir: Path
    datatype: str
    config: dict[str, Any] = field(default_factory=dict)

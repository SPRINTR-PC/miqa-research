"""The `inputs` reader every loader receives (#418, spec #402): the Job's staged originals.

`open(relative_path)` streams the staged copy (the runner keeps the per-Job scratch directory until the
Job is finalized); `record(relative_path)` returns its `EtlJobInput`, whose sha256 the runner stamped
while fetching. Only recorded paths are readable: nothing a script emits can reach another file.
"""
from pathlib import Path
from typing import BinaryIO

from MiqaResearch.data.models import EtlJobInput

from .exceptions import UnrecordedInput


class JobInputs:
    def __init__(self, entries: dict[str, tuple[EtlJobInput, Path]]):
        self._entries = entries

    @classmethod
    def from_staged(cls, pairs) -> JobInputs:
        """`pairs`: iterable of (relative_path, EtlJobInput, local Path)."""
        return cls({relative: (job_input, path) for relative, job_input, path in pairs})

    def _entry(self, relative_path: str) -> tuple[EtlJobInput, Path]:
        try:
            return self._entries[relative_path]
        except KeyError:
            raise UnrecordedInput(f"{relative_path!r} is not an input of this Job.") from None

    def open(self, relative_path: str) -> BinaryIO:
        return open(self._entry(relative_path)[1], "rb")

    def record(self, relative_path: str) -> EtlJobInput:
        return self._entry(relative_path)[0]

    def relative_paths(self) -> list[str]:
        return list(self._entries)


NO_INPUTS = JobInputs({})

"""The `SandboxBackend` interface (#161): one contract, two implementations selected via
`MIRES_SANDBOX_BACKEND` -- Compose here, Kubernetes in #165. The orchestrator (#162) is written
against this interface, never against a backend's own internals, and its own unit tests exercise
it against a fake implementation rather than a real container runtime.
"""
import abc
from collections.abc import Callable

from .spec import SandboxRunResult, SandboxRunSpec


class SandboxBackend(abc.ABC):
    @abc.abstractmethod
    def run(self, spec: SandboxRunSpec) -> SandboxRunResult:
        """Run `spec` to completion (or until its `limits.timeout_seconds` elapses) and return
        the result. Never raises for a Script's own failure -- that's carried in `exit_code`
        (see `etl_shim.contract`) -- only for a runner-level problem (unknown image, oversized
        input) that means no container was ever started.
        """

    @abc.abstractmethod
    def cancel(self, run_id: str) -> None:
        """Stop and remove the run identified by `run_id`, if it exists. A no-op if it doesn't
        (already finished, or never started).
        """

    @abc.abstractmethod
    def sweep(self, *, live_run_ids: Callable[[], set[str]]) -> None:
        """Remove any sandbox left behind by a crashed worker -- discovered via the backend's own
        bookkeeping (e.g. a label), not via in-memory state. A resource whose run id is in
        `live_run_ids()` is kept. That callback is only called *after* listing, so a run that
        starts between the two steps is never mistaken for an orphan (#225).
        """


def get_sandbox_backend() -> SandboxBackend:
    from django.conf import settings

    backend_name = settings.SANDBOX_BACKEND
    if backend_name == "compose":
        from .compose_backend import ComposeSandboxBackend
        return ComposeSandboxBackend()
    if backend_name == "kubernetes":
        from .kubernetes_backend import KubernetesSandboxBackend
        return KubernetesSandboxBackend()
    raise ValueError(f"Unknown MIRES_SANDBOX_BACKEND: {backend_name!r}")

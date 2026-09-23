"""Sandbox resource limits (#161): the platform defaults from #156's spec (10 minute timeout,
1 GiB memory, 1 CPU, 128 pids per run, 15 GiB input / 1 GiB output caps), with a `PipelineBinding`
allowed to lower -- never raise -- its timeout/memory/CPU below them. `pids_limit` and the
input/output byte caps have no override field on `PipelineBinding` (#144) and always come from the
platform default.
"""
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: int
    memory_mb: int
    cpu_millicores: int
    pids_limit: int
    max_input_bytes: int
    max_output_bytes: int


def platform_default_limits() -> SandboxLimits:
    return SandboxLimits(
        timeout_seconds=settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS,
        memory_mb=settings.SANDBOX_DEFAULT_MEMORY_MB,
        cpu_millicores=settings.SANDBOX_DEFAULT_CPU_MILLICORES,
        pids_limit=settings.SANDBOX_DEFAULT_PIDS_LIMIT,
        max_input_bytes=settings.SANDBOX_MAX_INPUT_BYTES,
        max_output_bytes=settings.SANDBOX_MAX_OUTPUT_BYTES,
    )


def resolve_limits(binding=None) -> SandboxLimits:
    """`binding` is a `PipelineBinding` (or `None` for the platform defaults untouched, e.g. a
    native script's own conformance run). Only accepts an object with the three override
    attributes rather than importing the model directly, so this stays exercisable without a
    database in unit tests.
    """
    defaults = platform_default_limits()
    if binding is None:
        return defaults
    return SandboxLimits(
        timeout_seconds=_clamp(binding.timeout_seconds_override, defaults.timeout_seconds),
        memory_mb=_clamp(binding.memory_mb_override, defaults.memory_mb),
        cpu_millicores=_clamp(binding.cpu_millicores_override, defaults.cpu_millicores),
        pids_limit=defaults.pids_limit,
        max_input_bytes=defaults.max_input_bytes,
        max_output_bytes=defaults.max_output_bytes,
    )


def _clamp(override: int | None, default: int) -> int:
    if override is None:
        return default
    return min(override, default)

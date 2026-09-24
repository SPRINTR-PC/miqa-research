class UnknownSandboxImage(Exception):
    """Raised when a Script's `image_key` isn't in the platform's key->digest allowlist. Raised
    before any container is created -- a Script can never select an arbitrary or unpinned image.
    """


class SandboxInputTooLarge(Exception):
    """Raised when a run's staged input (script source + input files) exceeds its `SandboxLimits.
    max_input_bytes`, checked before any container is created.
    """


class SandboxBackendUnhealthy(Exception):
    """Raised when a backend's own fail-closed self-test can't confirm its isolation guarantees hold --
    e.g. the Kubernetes backend's egress probe from a `default-deny-egress`-selected pod actually
    succeeded (the CNI silently doesn't enforce NetworkPolicy). A runner-level problem, not a Script's own
    failure: raised before any Job is scheduled.
    """

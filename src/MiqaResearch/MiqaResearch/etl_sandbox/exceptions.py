class UnknownSandboxImage(Exception):
    """Raised when a Script's `image_key` isn't in the platform's key->digest allowlist. Raised
    before any container is created -- a Script can never select an arbitrary or unpinned image.
    """


class SandboxInputTooLarge(Exception):
    """Raised when a run's staged input (script source + input files) exceeds its `SandboxLimits.
    max_input_bytes`, checked before any container is created.
    """

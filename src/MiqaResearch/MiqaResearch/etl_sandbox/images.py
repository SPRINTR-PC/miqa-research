"""The sandbox image key->digest allowlist (#161): a Script's Binding/Job carries an `image_key`
(language + runtime + release, per #147), never a raw image reference -- resolving it through this
allowlist, enforced here in runner code rather than trusted from the tag, is what stops a Script
from ever selecting an arbitrary or unpinned image. Operator-curated via `MIRES_SANDBOX_IMAGE_ALLOWLIST`
(a JSON object of key -> image reference); in production that reference should be a fully
digest-pinned tag (e.g. `registry/mires-etl-sandbox-python@sha256:...`), pinned once CI has built
and run each image's conformance suite (#147). Local dev/test may point a key at a mutable tag.
"""
from django.conf import settings

from .exceptions import UnknownSandboxImage


def resolve_sandbox_image(image_key: str) -> str:
    allowlist = settings.SANDBOX_IMAGE_ALLOWLIST
    try:
        return allowlist[image_key]
    except KeyError:
        raise UnknownSandboxImage(f"Sandbox image key {image_key!r} is not in the allowlist.") from None

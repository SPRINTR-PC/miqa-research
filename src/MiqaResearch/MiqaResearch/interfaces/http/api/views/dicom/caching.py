"""HTTP caching for WADO responses (#276).

`/frames` bytes never change for a given stored file + frame list, so the
browser keeps them (`private, max-age=31536000, immutable`, Vary: Accept).
`/metadata` goes through the De-identification Profile, so it is revalidated
on every use (`private, no-cache`) and answers 304 when its ETag still matches.
Both are `private`: shared caches must never hold participant data.
Visibility is always checked before a 304 is given.
"""
import hashlib

from django.http import HttpResponse
from django.utils.cache import patch_vary_headers
from django.utils.http import parse_etags

FRAMES_CACHE_CONTROL = "private, max-age=31536000, immutable"
METADATA_CACHE_CONTROL = "private, no-cache"


def strong_etag(*parts: str | bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part if isinstance(part, bytes) else part.encode())
        digest.update(b"\0")
    return f'"{digest.hexdigest()}"'


def matches_if_none_match(request, etag: str) -> bool:
    """Weak comparison, as RFC 9110 §13.1.2 prescribes for If-None-Match."""
    header = request.headers.get("If-None-Match")
    if not header:
        return False
    candidates = parse_etags(header)
    return "*" in candidates or etag in {candidate.removeprefix("W/") for candidate in candidates}


def with_cache_headers(response: HttpResponse, etag: str, cache_control: str, vary: tuple[str, ...] = ()) -> HttpResponse:
    response["ETag"] = etag
    response["Cache-Control"] = cache_control
    if vary:
        patch_vary_headers(response, vary)
    return response


def not_modified(etag: str, cache_control: str, vary: tuple[str, ...] = ()) -> HttpResponse:
    return with_cache_headers(HttpResponse(status=304), etag, cache_control, vary)

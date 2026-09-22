"""Discovery stage: resolve and list a run's source (#99, #114, #120).

A run's source is exactly one of:
- a local file path,
- a local folder path (scanned fully recursively, in deterministic order), or
- an S3 ``s3://bucket[/prefix]`` location.

Source-level problems are ``SourceError``s and fail the run immediately —
deliberately distinct from a run that completes having found zero files:
- ``SourceNotFoundError`` — the local source path does not exist,
- ``SourceInaccessibleError`` — it exists but cannot be listed/read,
- ``SourceNotAllowedError`` — a local source lies outside the configured
  allow-list of permitted base directories (checked before any file is read),
- ``S3SourceError`` — the S3 bucket does not exist, or cannot be listed/read
  with the configured credentials.

Per-file problems (a file that isn't DICOM, a vanishing S3 object mid-run) are
the pipeline's concern and are reported per file, never raised from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import boto3
from botocore.exceptions import ClientError


class SourceError(Exception):
    """The run's source cannot be used; the run fails immediately."""


class SourceNotFoundError(SourceError):
    """The local source path does not exist."""


class SourceInaccessibleError(SourceError):
    """The local source exists but cannot be listed or read."""


class SourceNotAllowedError(SourceError):
    """The local source lies outside the configured allow-list of base directories."""


class S3SourceError(SourceError):
    """The S3 source bucket does not exist or cannot be listed/read."""


def assert_local_source_allowed(path: str | Path, allowed_roots: Sequence[str | Path]) -> Path:
    """Resolve `path` and ensure it sits inside one of `allowed_roots`.

    Returns the resolved path. Raises SourceNotAllowedError — before any file
    read — when it does not, including when no roots are configured at all
    (default-deny). Symlinks are resolved, so a link escaping an allowed root
    is rejected.
    """
    resolved = Path(path).expanduser().resolve()
    for root in allowed_roots:
        root_resolved = Path(root).expanduser().resolve()
        if resolved == root_resolved or root_resolved in resolved.parents:
            return resolved
    raise SourceNotAllowedError(f"source path is outside the allowed source roots: {path}")


def discover_local_files(source: str | Path, allowed_roots: Sequence[str | Path]) -> list[Path]:
    """List every file under a local file/folder source, in deterministic order.

    Raises SourceNotFoundError / SourceInaccessibleError / SourceNotAllowedError
    (all fail the run immediately) for source-level problems.
    """
    resolved = assert_local_source_allowed(source, allowed_roots)
    if not resolved.exists():
        raise SourceNotFoundError(f"source does not exist: {source}")
    if resolved.is_file():
        return [resolved]
    if resolved.is_dir():
        try:
            # Symlinked directories are not followed (pathlib default); symlinked
            # files are still yielded and re-checked against the allow-list before
            # any read, so a link escaping an allowed root is rejected per file.
            return sorted(
                p for p in resolved.rglob("*")
                if p.is_file() or (p.is_symlink() and not p.is_dir())
            )
        except OSError as exc:
            raise SourceInaccessibleError(f"source cannot be listed: {source}") from exc
    raise SourceInaccessibleError(f"source is not a readable file or folder: {source}")


@dataclass(frozen=True)
class S3ObjectRef:
    """One object under an S3 source, addressed by bucket + key."""

    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def parse_s3_source(source: str) -> tuple[str, str]:
    """Split an ``s3://bucket[/prefix]`` source into (bucket, prefix)."""
    if not isinstance(source, str) or not source.startswith("s3://"):
        raise SourceError(f"not an S3 source: {source!r}")
    bucket, _, prefix = source[len("s3://"):].partition("/")
    if not bucket:
        raise SourceError(f"S3 source has no bucket: {source!r}")
    return bucket, prefix


class S3Source:
    """An opened S3 bucket/prefix source: validated, listable, readable, and
    (for source retention, #123) deletable one object at a time.

    Uses its own boto3 client, independent of the storage-write path (#99).
    Object keys are opaque strings here — they are never used to build local
    filesystem paths; the pipeline processes the bytes directly.
    """

    def __init__(self, source: str):
        self.bucket, self.prefix = parse_s3_source(source)
        self._client = _build_s3_client()
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", "?")
            raise S3SourceError(f"S3 source not accessible: bucket '{self.bucket}' (HTTP {status})") from exc

    def list_objects(self) -> list[S3ObjectRef]:
        """Every object under the source's bucket/prefix (zero-byte directory markers excluded)."""
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            page_kwargs = {"Bucket": self.bucket}
            if self.prefix:
                page_kwargs["Prefix"] = self.prefix
            refs = []
            for page in paginator.paginate(**page_kwargs):
                for obj in page.get("Contents", ()):
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue
                    refs.append(S3ObjectRef(self.bucket, key))
            return refs
        except ClientError as exc:
            raise S3SourceError(f"S3 source cannot be listed: bucket '{self.bucket}'") from exc

    def read(self, ref: S3ObjectRef) -> bytes:
        """The raw bytes of one object (S3SourceError when it can't be read)."""
        try:
            return self._client.get_object(Bucket=ref.bucket, Key=ref.key)["Body"].read()
        except ClientError as exc:
            raise S3SourceError(f"S3 object unreadable: {ref.uri}") from exc

    def delete(self, ref: S3ObjectRef) -> None:
        """Delete exactly this object (source retention, #123). S3SourceError when it can't be deleted."""
        try:
            self._client.delete_object(Bucket=ref.bucket, Key=ref.key)
        except ClientError as exc:
            raise S3SourceError(f"S3 object could not be deleted: {ref.uri}") from exc


def _build_s3_client():
    """The run's read-scoped S3 client, built from the DICOM S3 settings."""
    from django.conf import settings as django_settings

    kwargs: dict = {}
    if django_settings.DICOM_S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = django_settings.DICOM_S3_ENDPOINT_URL
    if django_settings.DICOM_S3_REGION_NAME:
        kwargs["region_name"] = django_settings.DICOM_S3_REGION_NAME
    if django_settings.DICOM_S3_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = django_settings.DICOM_S3_ACCESS_KEY_ID
    if django_settings.DICOM_S3_SECRET_ACCESS_KEY:
        kwargs["aws_secret_access_key"] = django_settings.DICOM_S3_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)

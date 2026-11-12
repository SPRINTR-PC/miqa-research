"""The ETL orchestrator's (#162) S3-compatible bucket source: lists and reads a
`PipelineBinding`'s source bucket through the Binding's Connected Storage (#394; the Default storage is
the platform-wide `MIRES_ETL_S3_*` credential). Per-project isolation is enforced in application code --
`EtlLocationGrant` is that enforcement, checked by the caller, not here).

Deliberately its own client, independent of the sandbox runner's and the DICOM ingestion
pipeline's own S3 wrappers -- each is scoped to a different credential and bucket set.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class EtlBucketSourceError(Exception):
    """A source bucket can't be listed or an object can't be read this poll. Callers scope this
    to the one Binding being polled -- another Binding's poll is unaffected."""


@dataclass(frozen=True)
class EtlObjectRef:
    bucket: str
    key: str
    etag: str
    last_modified: datetime | None
    size: int = 0


class EtlBucketSource:
    def __init__(self, bucket: str, prefix: str, storage):
        self.bucket = bucket
        self.prefix = prefix
        self._client = build_storage_client(storage)

    def list_objects(self) -> list[EtlObjectRef]:
        """Every object under this source's bucket/prefix, zero-byte directory markers excluded."""
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
                    refs.append(EtlObjectRef(
                        bucket=self.bucket, key=key,
                        etag=obj.get("ETag", "").strip('"'),
                        last_modified=obj.get("LastModified"), size=obj.get("Size", 0),
                    ))
            return refs
        except ClientError as exc:
            raise EtlBucketSourceError(f"ETL source bucket cannot be listed: {self.bucket!r}") from exc

    def read(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise EtlBucketSourceError(f"ETL source object unreadable: {self.bucket}/{key}") from exc

    def size_of(self, key: str) -> int:
        """The object's current size per S3 (HEAD), the 'listed size' the runner admits and verifies against."""
        try:
            return self._client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except ClientError as exc:
            raise EtlBucketSourceError(f"ETL source object unreadable: {self.bucket}/{key}") from exc

    def download(self, key: str, destination: Path) -> tuple[str, int]:
        """Stream `key` to `destination` in chunks, returning `(sha256 hex, byte count)` computed in the same
        pass; RAM is bounded by one chunk however large the object (#414)."""
        digest, size = hashlib.sha256(), 0
        try:
            body = self._client.get_object(Bucket=self.bucket, Key=key)["Body"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(destination, "wb") as out:
                for chunk in body.iter_chunks(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        except ClientError as exc:
            raise EtlBucketSourceError(f"ETL source object unreadable: {self.bucket}/{key}") from exc
        return digest.hexdigest(), size


class EtlStorageCredentialsNotConfigured(Exception):
    """A Connected Storage has no credentials: env vars unset and Vault off, unreachable or unseeded."""


def build_storage_client(storage, *, config=None):
    """The S3 client for one Connected Storage (#394). The Default storage is the platform-wide
    MIRES_ETL_S3_* settings, read live; any other reads the env vars / Vault secrets it names (#396)."""
    if storage.is_default:
        return build_etl_s3_client(config=config)
    credentials = storage.resolve_credentials()
    if credentials is None:
        raise EtlStorageCredentialsNotConfigured(f"Storage {storage.name!r}: credentials not configured")
    kwargs: dict = {"aws_access_key_id": credentials[0], "aws_secret_access_key": credentials[1]}
    if storage.endpoint_url:
        kwargs["endpoint_url"] = storage.endpoint_url
    if storage.region:
        kwargs["region_name"] = storage.region
    if config is not None:
        kwargs["config"] = config
    return boto3.client("s3", **kwargs)


def build_etl_s3_client(*, config=None):
    from django.conf import settings

    kwargs: dict = {}
    if settings.ETL_S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.ETL_S3_ENDPOINT_URL
    if settings.ETL_S3_REGION_NAME:
        kwargs["region_name"] = settings.ETL_S3_REGION_NAME
    if settings.ETL_S3_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.ETL_S3_ACCESS_KEY_ID
    if settings.ETL_S3_SECRET_ACCESS_KEY:
        kwargs["aws_secret_access_key"] = settings.ETL_S3_SECRET_ACCESS_KEY
    if config is not None:
        kwargs["config"] = config
    return boto3.client("s3", **kwargs)


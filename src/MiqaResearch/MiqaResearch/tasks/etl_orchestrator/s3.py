"""The ETL orchestrator's (#162) S3-compatible bucket source: lists and reads a
`PipelineBinding`'s source bucket via the platform-wide `MIRES_ETL_S3_*` credential (per #156's
"one platform-wide service credential... per-project isolation enforced in application code"
decision -- `EtlLocationGrant` is that enforcement, checked by the caller, not here).

Deliberately its own client, independent of the sandbox runner's and the DICOM ingestion
pipeline's own S3 wrappers -- each is scoped to a different credential and bucket set.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


class EtlBucketSourceError(Exception):
    """A source bucket can't be listed or an object can't be read this poll. Callers scope this
    to the one Binding being polled -- another Binding's poll is unaffected."""


@dataclass(frozen=True)
class EtlObjectRef:
    bucket: str
    key: str
    etag: str
    last_modified: datetime | None


class EtlBucketSource:
    def __init__(self, bucket: str, prefix: str = ""):
        self.bucket = bucket
        self.prefix = prefix
        self._client = build_etl_s3_client()

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
                        last_modified=obj.get("LastModified"),
                    ))
            return refs
        except ClientError as exc:
            raise EtlBucketSourceError(f"ETL source bucket cannot be listed: {self.bucket!r}") from exc

    def read(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise EtlBucketSourceError(f"ETL source object unreadable: {self.bucket}/{key}") from exc


def build_etl_s3_client():
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
    return boto3.client("s3", **kwargs)

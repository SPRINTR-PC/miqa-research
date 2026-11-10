"""Read-only browsing of a Connected Storage (#394): its buckets, then one folder level at a time
(common prefixes) plus up to `MAX_OBJECT_NAMES` object names for orientation. Never object contents.
Every failure is an `EtlStorageBrowseError` with a message safe to show staff inline."""
from dataclasses import dataclass, field

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from MiqaResearch.tasks.etl_orchestrator.s3 import EtlStorageCredentialsNotConfigured, build_storage_client

MAX_OBJECT_NAMES = 50
_BROWSE_CONFIG = Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 1})


class EtlStorageBrowseError(Exception):
    """The storage can't be browsed right now; the message says why, and typing stays possible."""


@dataclass
class StorageListing:
    buckets: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    objects_truncated: bool = False


def list_buckets(storage) -> StorageListing:
    client = _client(storage)
    try:
        response = client.list_buckets()
    except (ClientError, BotoCoreError) as exc:
        raise _browse_error(exc, "list buckets") from exc
    return StorageListing(buckets=sorted(bucket["Name"] for bucket in response.get("Buckets", ())))


def list_folder(storage, bucket: str, prefix: str = "") -> StorageListing:
    client = _client(storage)
    try:
        response = client.list_objects_v2(
            Bucket=bucket, Prefix=prefix, Delimiter="/", MaxKeys=1000)
    except (ClientError, BotoCoreError) as exc:
        raise _browse_error(exc, "list this location") from exc
    names = [
        obj["Key"] for obj in response.get("Contents", ())
        if obj["Key"] != prefix and not obj["Key"].endswith("/")]
    return StorageListing(
        folders=[common["Prefix"] for common in response.get("CommonPrefixes", ())],
        objects=names[:MAX_OBJECT_NAMES],
        objects_truncated=len(names) > MAX_OBJECT_NAMES or bool(response.get("IsTruncated")),
    )


def _client(storage):
    try:
        return build_storage_client(storage, config=_BROWSE_CONFIG)
    except EtlStorageCredentialsNotConfigured as exc:
        raise EtlStorageBrowseError(str(exc)) from exc


def _browse_error(exc: Exception, action: str) -> EtlStorageBrowseError:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("AccessDenied", "AllAccessDisabled", "Forbidden", "403"):
            return EtlStorageBrowseError(f"Access denied: the credential may not {action}.")
        if code in ("NoSuchBucket", "404"):
            return EtlStorageBrowseError("That bucket does not exist.")
        return EtlStorageBrowseError(f"The storage refused the request ({code or 'error'}).")
    if isinstance(exc, NoCredentialsError):
        return EtlStorageBrowseError("No credentials are configured for this storage.")
    return EtlStorageBrowseError("Could not reach the storage.")

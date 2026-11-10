"""Connected Storages (#394): browsing a storage's buckets and folders (read-only; one level at a
time; never file contents) and the `etl_storage_browsed` audit entry, which carries the storage and
bucket but never a prefix or object name."""
import json

import boto3
import pytest
from asgiref.sync import async_to_sync
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

from contract.constants.audit_log import EVENT_TYPE_ETL_STORAGE_BROWSED
from MiqaResearch.actions.etl.storages import browse_storage
from MiqaResearch.data.models import AuditLog, EtlStorage, ResearchProject
from MiqaResearch.data.models.etl_storage import default_storage
from MiqaResearch.readers.etl_storage_browser import EtlStorageBrowseError


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Browse project", description="")


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="alpha")
        client.create_bucket(Bucket="beta")
        yield client


def _browse(project, storage=None, **kwargs):
    return async_to_sync(browse_storage)(
        user=None, request=None, project=project, storage=storage or default_storage(), **kwargs)


def _audit():
    return list(AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_STORAGE_BROWSED))


def test_buckets_are_listed_and_the_audit_names_the_storage_but_no_bucket(project, s3):
    listing = _browse(project)

    assert listing.buckets == ["alpha", "beta"]
    [event] = _audit()
    assert event.metadata == {"etl_storage_id": str(default_storage().id)}
    assert event.project == project


def test_a_bucket_is_browsed_one_folder_level_at_a_time(project, s3):
    for key in ("a/x/1.csv", "a/y/2.csv", "a/top.csv", "b/other.csv", "root.csv"):
        s3.put_object(Bucket="alpha", Key=key, Body=b"secret contents")

    root = _browse(project, bucket="alpha")
    inside_a = _browse(project, bucket="alpha", prefix="a/")

    assert root.folders == ["a/", "b/"] and root.objects == ["root.csv"]
    assert inside_a.folders == ["a/x/", "a/y/"] and inside_a.objects == ["a/top.csv"]


def test_at_most_fifty_object_names_are_shown_per_folder(project, s3):
    for number in range(60):
        s3.put_object(Bucket="alpha", Key=f"f/{number:03}.csv", Body=b"x")

    listing = _browse(project, bucket="alpha", prefix="f/")

    assert len(listing.objects) == 50 and listing.objects_truncated


def test_the_audit_has_the_bucket_but_neither_prefix_nor_object_names(project, s3):
    s3.put_object(Bucket="alpha", Key="patients/jane-doe/scan.csv", Body=b"x")

    _browse(project, bucket="alpha", prefix="patients/jane-doe/")

    [event] = _audit()
    assert event.metadata == {"etl_storage_id": str(default_storage().id), "bucket": "alpha"}
    assert "jane-doe" not in json.dumps(event.metadata) and "scan.csv" not in json.dumps(event.metadata)


def test_unconfigured_credentials_are_a_clear_error(project, monkeypatch):
    monkeypatch.delenv("LAB_KEY", raising=False)
    lab = EtlStorage.objects.create(name="Lab", access_key_id_env="LAB_KEY", secret_access_key_env="LAB_SECRET")

    with pytest.raises(EtlStorageBrowseError, match="credentials not configured"):
        _browse(project, storage=lab)


class _FailingClient:
    def __init__(self, error):
        self.error = error

    def list_buckets(self, **kwargs):
        raise self.error

    def list_objects_v2(self, **kwargs):
        raise self.error


@pytest.mark.parametrize("error, message", [
    (ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "ListBuckets"), "denied"),
    (EndpointConnectionError(endpoint_url="http://down:9000"), "reach"),
])
def test_s3_failures_become_clear_browse_errors(project, monkeypatch, error, message):
    from MiqaResearch.readers import etl_storage_browser
    monkeypatch.setattr(etl_storage_browser, "build_storage_client", lambda storage, **kw: _FailingClient(error))

    with pytest.raises(EtlStorageBrowseError, match=message):
        _browse(project)
    with pytest.raises(EtlStorageBrowseError, match=message):
        _browse(project, bucket="alpha")

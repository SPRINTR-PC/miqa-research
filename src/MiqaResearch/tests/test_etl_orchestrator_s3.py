"""ETL orchestrator (#162): the S3-compatible bucket source the polling task lists/reads a
Binding's source bucket through. Mirrors the DICOM ingestion S3Source's own moto-mocked test
pattern (tests/test_dicom_discovery.py) -- an in-memory S3, no real endpoint needed.
"""
import boto3
import pytest
from moto import mock_aws

from MiqaResearch.tasks.etl_orchestrator.s3 import EtlBucketSource, EtlBucketSourceError


@pytest.fixture(autouse=True)
def etl_s3_settings(settings):
    settings.ETL_S3_ENDPOINT_URL = None
    settings.ETL_S3_REGION_NAME = "us-east-1"
    settings.ETL_S3_ACCESS_KEY_ID = "testing"
    settings.ETL_S3_SECRET_ACCESS_KEY = "testing"


@mock_aws
def test_list_objects_returns_every_object_under_the_prefix_recursively():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"a")
    client.put_object(Bucket="incoming", Key="redcap/sub/b.csv", Body=b"b")
    client.put_object(Bucket="incoming", Key="other/c.csv", Body=b"c")

    refs = EtlBucketSource("incoming", "redcap/").list_objects()

    assert sorted(ref.key for ref in refs) == ["redcap/a.csv", "redcap/sub/b.csv"]


@mock_aws
def test_list_objects_excludes_zero_byte_directory_markers():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/", Body=b"")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"a")

    refs = EtlBucketSource("incoming", "redcap/").list_objects()

    assert [ref.key for ref in refs] == ["redcap/a.csv"]


@mock_aws
def test_list_objects_with_no_prefix_lists_the_whole_bucket():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="a.csv", Body=b"a")
    client.put_object(Bucket="incoming", Key="deep/nest/b.csv", Body=b"b")

    refs = EtlBucketSource("incoming", "").list_objects()

    assert sorted(ref.key for ref in refs) == ["a.csv", "deep/nest/b.csv"]


@mock_aws
def test_list_objects_carries_etag_and_last_modified():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"a")

    [ref] = EtlBucketSource("incoming", "redcap/").list_objects()

    assert ref.etag
    assert '"' not in ref.etag
    assert ref.last_modified is not None


@mock_aws
def test_list_objects_raises_for_a_missing_bucket():
    with pytest.raises(EtlBucketSourceError):
        EtlBucketSource("no-such-bucket", "redcap/").list_objects()


@mock_aws
def test_read_returns_the_objects_bytes():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")
    client.put_object(Bucket="incoming", Key="redcap/a.csv", Body=b"hello world")

    data = EtlBucketSource("incoming", "redcap/").read("redcap/a.csv")

    assert data == b"hello world"


@mock_aws
def test_read_raises_for_a_missing_key():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="incoming")

    with pytest.raises(EtlBucketSourceError):
        EtlBucketSource("incoming", "redcap/").read("redcap/does-not-exist.csv")

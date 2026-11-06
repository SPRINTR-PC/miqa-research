"""Connected Storages (#394): the S3 client for a storage is built from that storage's own endpoint,
region and the env vars its credential names; the Default storage reads MIRES_ETL_S3_* live."""
import pytest

from MiqaResearch.data.models import EtlStorage
from MiqaResearch.data.models.etl_storage import default_storage
from MiqaResearch.tasks.etl_orchestrator.s3 import EtlStorageCredentialsNotConfigured, build_storage_client


def _creds(client):
    return client._request_signer._credentials


def test_default_storage_reads_settings_live(db, settings):
    storage = default_storage()
    settings.ETL_S3_ENDPOINT_URL = "http://one.example:9000"
    settings.ETL_S3_REGION_NAME = "eu-north-1"
    settings.ETL_S3_ACCESS_KEY_ID = "key-one"
    settings.ETL_S3_SECRET_ACCESS_KEY = "secret-one"
    client = build_storage_client(storage)
    assert client.meta.endpoint_url == "http://one.example:9000"
    assert client.meta.region_name == "eu-north-1"
    assert _creds(client).access_key == "key-one"

    settings.ETL_S3_ACCESS_KEY_ID = "key-two"  # changed after the storage row exists: no snapshot
    assert _creds(build_storage_client(storage)).access_key == "key-two"


def test_custom_storage_uses_its_own_endpoint_region_and_env_credentials(db, monkeypatch):
    monkeypatch.setenv("LAB_KEY", "lab-key")
    monkeypatch.setenv("LAB_SECRET", "lab-secret")
    storage = EtlStorage.objects.create(
        name="Lab", endpoint_url="http://lab.example:9000", region="eu-west-1",
        access_key_id_env="LAB_KEY", secret_access_key_env="LAB_SECRET")
    client = build_storage_client(storage)
    assert client.meta.endpoint_url == "http://lab.example:9000"
    assert client.meta.region_name == "eu-west-1"
    assert _creds(client).access_key == "lab-key"
    assert _creds(client).secret_key == "lab-secret"


def test_missing_env_var_is_credentials_not_configured(db, monkeypatch):
    monkeypatch.delenv("LAB_KEY", raising=False)
    monkeypatch.setenv("LAB_SECRET", "x")
    storage = EtlStorage.objects.create(
        name="Lab", endpoint_url="http://lab.example:9000", region="eu-west-1",
        access_key_id_env="LAB_KEY", secret_access_key_env="LAB_SECRET")
    assert storage.credentials_configured is False
    with pytest.raises(EtlStorageCredentialsNotConfigured, match="credentials not configured"):
        build_storage_client(storage)

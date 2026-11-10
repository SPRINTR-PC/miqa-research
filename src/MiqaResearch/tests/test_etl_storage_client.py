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


@pytest.fixture
def fake_vault(monkeypatch, settings):
    from MiqaResearch.data.models import etl_storage

    settings.USE_VAULT = True
    settings.VAULT_URL = "http://vault"
    settings.VAULT_TOKEN = "t"
    secrets = {("mires/lab", "Id"): "vault-key", ("mires/lab", "Secret"): "vault-secret"}

    def get_secret(client, path, name):
        return secrets[(path, name)]

    monkeypatch.setattr(etl_storage.vault, "get_vault_client", lambda url, token: object())
    monkeypatch.setattr(etl_storage.vault, "get_vault_secret", get_secret)
    return secrets


def _vault_storage(**extra):
    return EtlStorage.objects.create(
        name="Lab", endpoint_url="http://lab.example:9000", region="eu-west-1",
        access_key_id_vault_path="mires/lab", access_key_id_vault_key="Id",
        secret_access_key_vault_path="mires/lab", secret_access_key_vault_key="Secret", **extra)


def test_custom_storage_reads_credentials_from_vault(db, fake_vault):
    storage = _vault_storage()
    assert storage.credentials_configured is True
    client = build_storage_client(storage)
    assert _creds(client).access_key == "vault-key"
    assert _creds(client).secret_key == "vault-secret"


def test_env_var_wins_over_vault_per_credential(db, fake_vault, monkeypatch):
    monkeypatch.setenv("LAB_KEY", "env-key")
    monkeypatch.delenv("LAB_SECRET", raising=False)
    storage = _vault_storage(access_key_id_env="LAB_KEY", secret_access_key_env="LAB_SECRET")
    client = build_storage_client(storage)
    assert _creds(client).access_key == "env-key"
    assert _creds(client).secret_key == "vault-secret"


def test_vault_off_is_credentials_not_configured(db, fake_vault, settings):
    settings.USE_VAULT = False
    storage = _vault_storage()
    assert storage.credentials_configured is False
    with pytest.raises(EtlStorageCredentialsNotConfigured):
        build_storage_client(storage)


def test_unreachable_vault_is_credentials_not_configured(db, fake_vault, monkeypatch):
    from MiqaResearch.data.models import etl_storage

    def boom(client, path, name):
        raise RuntimeError("vault down")

    monkeypatch.setattr(etl_storage.vault, "get_vault_secret", boom)
    storage = _vault_storage()
    assert storage.credentials_configured is False
    with pytest.raises(EtlStorageCredentialsNotConfigured):
        build_storage_client(storage)

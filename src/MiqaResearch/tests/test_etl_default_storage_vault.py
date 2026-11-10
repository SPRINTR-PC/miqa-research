import pytest

from MiqaResearch import settings as project_settings


@pytest.fixture
def fake_env(monkeypatch):
    values = {
        "MIRES_ETL_S3_ACCESS_KEY_ID": None,
        "MIRES_ETL_S3_SECRET_ACCESS_KEY": None,
        "MIRES_USE_VAULT": True,
        "MIRES_VAULT_URL": "http://vault",
        "MIRES_VAULT_TOKEN": "t",
        "MIRES_ETL_S3_VAULT_PATH": "mires/etl-s3",
    }
    monkeypatch.setattr(project_settings, "env", values.__getitem__)
    return values


@pytest.fixture
def fake_vault(monkeypatch):
    secrets = {"AccessKeyId": "vault-id", "SecretAccessKey": "vault-secret"}
    monkeypatch.setattr(project_settings.vault, "get_vault_client", lambda url, token: object())
    monkeypatch.setattr(project_settings.vault, "get_vault_secret", lambda client, path, name: secrets[name])
    return secrets


def test_default_storage_credentials_come_from_vault_when_env_is_unset(fake_env, fake_vault):
    assert project_settings._get_etl_s3_credentials() == ("vault-id", "vault-secret")


def test_env_credentials_win_over_vault(fake_env, fake_vault):
    fake_env["MIRES_ETL_S3_ACCESS_KEY_ID"] = "env-id"
    fake_env["MIRES_ETL_S3_SECRET_ACCESS_KEY"] = "env-secret"
    assert project_settings._get_etl_s3_credentials() == ("env-id", "env-secret")


def test_vault_is_not_read_when_disabled(fake_env, fake_vault):
    fake_env["MIRES_USE_VAULT"] = False
    assert project_settings._get_etl_s3_credentials() == (None, None)


def test_unseeded_vault_leaves_credentials_unset(fake_env, fake_vault):
    del fake_vault["SecretAccessKey"]
    fake_vault.clear()
    assert project_settings._get_etl_s3_credentials() == (None, None)

import logging

import hvac

logger = logging.getLogger(__name__)


def get_vault_client(url: str, token: str) -> hvac.Client:
    return hvac.Client(url=url, token=token)


def get_vault_secret(vault_client: hvac.Client, path: str, secret_name: str):
    try:
        read_response = vault_client.secrets.kv.v2.read_secret_version(path=path)
        secret = read_response["data"]["data"][secret_name]
    except Exception:
        logger.error("Error reading secret from Vault", exc_info=True)
        raise

    return secret


def get_data_encryption_keys(env, fernet_key_encryption: str = "utf-8") -> tuple[bytes, str]:
    """Fetches the data encryption keys from Vault.

    Returns:
        Fernet key and the sensitive data hash key in a tuple
    """
    vault_client = get_vault_client(
        url=env("MIRES_VAULT_URL"),
        token=env("MIRES_VAULT_TOKEN"),
    )

    fernet_key = get_vault_secret(vault_client, env("MIRES_DATA_HASH_KEY_VAULT_PATH"), "FernetKey")
    hash_key = get_vault_secret(vault_client, env("MIRES_DATA_HASH_KEY_VAULT_PATH"), "SensitiveDataHashKey")

    return fernet_key.encode(fernet_key_encryption), hash_key



def get_consent_client_id_and_secret(env):
    if env("MIRES_TASK_CONSENT_SKIP_CLIENT"):
        return None, None

    client_id = env("MIRES_TASK_CONSENT_CLIENT_ID")
    client_secret = env("MIRES_TASK_CONSENT_CLIENT_SECRET")
    if client_id is None or client_secret is None:
        vault_client = get_vault_client(
            url=env("MIRES_VAULT_URL"),
            token=env("MIRES_VAULT_TOKEN"),
        )
        return (
            get_vault_secret(vault_client, env("MIRES_TASK_CONSENT_VAULT_PATH"), "ConsentClientId"),
            get_vault_secret(vault_client, env("MIRES_TASK_CONSENT_VAULT_PATH"), "ConsentClientSecret"),
        )
    return client_id, client_secret

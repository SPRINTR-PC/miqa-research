import logging

import hvac

logger = logging.getLogger(__name__)


def get_vault_client(url: str, token: str) -> hvac.Client:
    return hvac.Client(url=url, token=token)


def get_vault_secret(vault_client: hvac.Client, path: str, secret_name: str):
    try:
        read_response = vault_client.secrets.kv.read_secret_version(path=path)
        secret = read_response["data"]["data"][secret_name]
    except Exception as e:
        logger.error(f"Error reading secret from Vault", exc_info=True)
        raise
    
    return secret


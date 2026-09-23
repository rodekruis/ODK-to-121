"""Secret lookup: the environment first, Azure Key Vault as the fallback in prod."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from odk_to_121.data_types.config_types import Environment

if TYPE_CHECKING:
    from azure.keyvault.secrets import SecretClient

logger = logging.getLogger(__name__)

KEY_VAULT_URL_VAR = "AZURE_KEY_VAULT_URL"


class SecretsError(RuntimeError):
    """Raised when Key Vault is configured but cannot be read."""


class SecretProvider:
    """Resolves one secret at a time. One instance per run, so lookups are cached."""

    def __init__(self, key_vault_url: str | None = None):
        """Without a vault url the provider reads the environment only."""
        self.key_vault_url = key_vault_url
        self._client: SecretClient | None = None
        self._cache: dict[str, str] = {}

    @classmethod
    def for_environment(cls, environment: Environment) -> SecretProvider:
        """Only prod may reach out to Key Vault; debug and test stay offline."""
        if environment is not Environment.PROD:
            return cls()

        key_vault_url = os.environ.get(KEY_VAULT_URL_VAR)
        if not key_vault_url:
            logger.info(
                "%s is not set, reading secrets from the environment only", KEY_VAULT_URL_VAR
            )
        return cls(key_vault_url)

    def get(self, name: str) -> str | None:
        """Return the value of one secret, or None when neither source holds it."""
        value = os.environ.get(name)
        if value:
            return value
        if not self.key_vault_url:
            return None
        return self._from_key_vault(name, self.key_vault_url)

    def _from_key_vault(self, name: str, key_vault_url: str) -> str | None:
        """Fetch one secret from the vault. A missing secret is not an error; a broken vault is."""
        if name in self._cache:
            return self._cache[name]

        # Imported here so runs without a vault do not pay for the Azure SDK import.
        from azure.core.exceptions import AzureError, ResourceNotFoundError

        secret_name = to_key_vault_name(name)
        try:
            secret = self._get_client(key_vault_url).get_secret(secret_name)
        except ResourceNotFoundError:
            logger.warning("Key Vault %s holds no secret '%s'", key_vault_url, secret_name)
            return None
        except AzureError as exc:
            raise SecretsError(
                f"Key Vault {key_vault_url}: cannot read secret '{secret_name}': {exc}"
            ) from exc

        if not secret.value:
            logger.warning("Key Vault secret '%s' is empty", secret_name)
            return None

        self._cache[name] = secret.value
        logger.info("Read secret '%s' from Key Vault", secret_name)
        return secret.value

    def _get_client(self, key_vault_url: str) -> SecretClient:
        """Build the vault client on the first miss only."""
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            self._client = SecretClient(
                vault_url=key_vault_url, credential=DefaultAzureCredential()
            )
        return self._client


def to_key_vault_name(name: str) -> str:
    """Key Vault names allow only letters, digits and dashes, so ODK_BASE_URL is ODK-BASE-URL."""
    return name.replace("_", "-")

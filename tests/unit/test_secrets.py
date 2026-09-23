from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.keyvault.secrets import SecretClient

from odk_to_121.data_types.config_types import Environment
from odk_to_121.utils.secrets import (
    KEY_VAULT_URL_VAR,
    SecretProvider,
    SecretsError,
    to_key_vault_name,
)

VAULT_URL = "https://vault.test"


class FakeVault:
    """Stands in for azure SecretClient; records every name it was asked for."""

    def __init__(self, secrets: dict[str, Any]):
        self.secrets = secrets
        self.requested: list[str] = []

    def get_secret(self, name: str) -> Any:
        self.requested.append(name)
        value = self.secrets.get(name)
        if value is None:
            raise ResourceNotFoundError(f"no secret {name}")
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(value=value)


def _provider(vault: FakeVault, key_vault_url: str | None = VAULT_URL) -> SecretProvider:
    provider = SecretProvider(key_vault_url)
    provider._client = cast(SecretClient, vault)
    return provider


def test_the_environment_wins_over_the_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ODK_PASSWORD", "from-env")
    vault = FakeVault({"ODK-PASSWORD": "from-vault"})

    assert _provider(vault).get("ODK_PASSWORD") == "from-env"
    assert vault.requested == []


def test_a_missing_variable_falls_back_to_the_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ODK_PASSWORD", raising=False)
    vault = FakeVault({"ODK-PASSWORD": "from-vault"})

    assert _provider(vault).get("ODK_PASSWORD") == "from-vault"
    assert vault.requested == ["ODK-PASSWORD"]


def test_repeated_lookups_hit_the_vault_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("URL_121", raising=False)
    vault = FakeVault({"URL-121": "https://121.test"})
    provider = _provider(vault)

    provider.get("URL_121")
    provider.get("URL_121")

    assert vault.requested == ["URL-121"]


def test_a_secret_the_vault_does_not_hold_reads_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client then raises its own 'missing credentials' error, as without a vault."""
    monkeypatch.delenv("ODK_USERNAME", raising=False)

    assert _provider(FakeVault({})).get("ODK_USERNAME") is None


def test_a_broken_vault_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ODK_USERNAME", raising=False)
    vault = FakeVault({"ODK-USERNAME": AzureError("forbidden")})

    with pytest.raises(SecretsError, match="ODK-USERNAME"):
        _provider(vault).get("ODK_USERNAME")


def test_without_a_vault_url_only_the_environment_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ODK_USERNAME", raising=False)
    vault = FakeVault({"ODK-USERNAME": "from-vault"})

    assert _provider(vault, key_vault_url=None).get("ODK_USERNAME") is None
    assert vault.requested == []


@pytest.mark.parametrize("environment", [Environment.DEBUG, Environment.TEST])
def test_only_prod_may_reach_out_to_the_vault(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY_VAULT_URL_VAR, VAULT_URL)

    assert SecretProvider.for_environment(environment).key_vault_url is None
    assert SecretProvider.for_environment(Environment.PROD).key_vault_url == VAULT_URL


def test_prod_without_a_configured_vault_stays_on_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(KEY_VAULT_URL_VAR, raising=False)

    assert SecretProvider.for_environment(Environment.PROD).key_vault_url is None


def test_underscores_become_dashes() -> None:
    assert to_key_vault_name("ODK_BASE_URL") == "ODK-BASE-URL"

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from odk_to_121.utils.logging_config import (
    CONNECTION_STRING_VAR,
    PACKAGE_LOGGER,
    RunIdFilter,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """configure_logging mutates global state, so put the package logger back afterwards."""
    package_logger = logging.getLogger(PACKAGE_LOGGER)
    handlers = list(package_logger.handlers)
    yield
    package_logger.handlers = handlers


def test_no_connection_string_means_no_azure_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONNECTION_STRING_VAR, raising=False)

    configure_logging("abc123")

    assert logging.getLogger(PACKAGE_LOGGER).handlers == []


def test_an_empty_connection_string_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONNECTION_STRING_VAR, "")

    configure_logging("abc123")

    assert logging.getLogger(PACKAGE_LOGGER).handlers == []


def test_the_run_id_travels_as_a_record_attribute() -> None:
    record = logging.LogRecord(PACKAGE_LOGGER, logging.INFO, __file__, 1, "msg", None, None)

    assert RunIdFilter("abc123").filter(record)
    # Read via __dict__: the attribute is injected, so it is not on the LogRecord type.
    assert record.__dict__["run_id"] == "abc123"

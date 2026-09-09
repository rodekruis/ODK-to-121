from __future__ import annotations

import time

from odk_to_121.utils.client_121 import Client121


def _client(seconds_between_registrations: float) -> Client121:
    """A client that is never actually called; only its pacing is under test."""
    return Client121(
        "https://121.test",
        "user",
        "secret",
        seconds_between_registrations=seconds_between_registrations,
    )


def test_the_first_registration_is_not_delayed() -> None:
    client = _client(10)

    start = time.monotonic()
    client._pace_registrations()

    assert time.monotonic() - start < 1


def test_registrations_are_spaced_out() -> None:
    interval = 0.05
    client = _client(interval)

    start = time.monotonic()
    client._pace_registrations()
    client._pace_registrations()

    assert time.monotonic() - start >= interval


def test_time_already_spent_counts_towards_the_interval() -> None:
    """Pacing must not add a full interval on top of a slow request."""
    interval = 0.05
    client = _client(interval)

    client._pace_registrations()
    time.sleep(interval)
    start = time.monotonic()
    client._pace_registrations()

    assert time.monotonic() - start < interval

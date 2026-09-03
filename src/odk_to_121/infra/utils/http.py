"""Shared HTTP session with retries and timeouts."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 30


def create_resilient_session(
    *,
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    allowed_methods: tuple[str, ...] = ("GET",),
) -> requests.Session:
    """Session that retries idempotent calls on 429/5xx with exponential backoff."""
    session = requests.Session()
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=list(allowed_methods),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

"""121 platform client: login, create and update registrations."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from odk_to_121.infra.data_types.domain_types import Scalar
from odk_to_121.infra.utils.http import DEFAULT_TIMEOUT, create_resilient_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000


class Client121Error(RuntimeError):
    """Raised when the 121 platform cannot be reached or authenticated against."""


class Client121:
    """Client for the 121 platform. One instance per run."""

    def __init__(
        self, base_url: str, username: str, password: str, *, timeout: int = DEFAULT_TIMEOUT
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self.timeout = timeout
        self.session = create_resilient_session()
        self._logged_in = False

    @classmethod
    def from_env(cls) -> Client121:
        base_url = os.environ.get("URL_121")
        username = os.environ.get("USERNAME_121")
        password = os.environ.get("PASSWORD_121")
        if not (base_url and username and password):
            raise Client121Error("Missing URL_121, USERNAME_121 or PASSWORD_121")
        return cls(base_url, username, password)

    def login(self) -> None:
        """Authenticate; the access token is kept as a session cookie."""
        response = self.session.post(
            f"{self.base_url}/api/users/login",
            json={"username": self._username, "password": self._password},
            timeout=self.timeout,
        )
        if response.status_code not in range(200, 300):
            raise Client121Error(f"121 login failed with status {response.status_code}")
        self._logged_in = True
        logger.info("Authenticated against 121 at %s", self.base_url)

    def get_reference_ids(self, program_id: int) -> set[str]:
        """Return the reference ids already registered in a program."""
        self._ensure_login()
        url = f"{self.base_url}/api/programs/{program_id}/registrations"
        reference_ids: set[str] = set()
        page = 1
        while True:
            response = self.session.get(
                url, params={"limit": PAGE_SIZE, "page": page}, timeout=self.timeout
            )
            response.raise_for_status()
            batch = _extract_records(response.json())
            reference_ids.update(
                str(record["referenceId"]) for record in batch if record.get("referenceId")
            )
            if len(batch) < PAGE_SIZE:
                break
            page += 1
        logger.info("Program %d already holds %d registrations", program_id, len(reference_ids))
        return reference_ids

    def get_registration_attributes(self, program_id: int) -> dict[str, str]:
        """Return the program's registration attributes as name -> type."""
        self._ensure_login()
        response = self.session.get(
            f"{self.base_url}/api/programs/{program_id}/attributes", timeout=self.timeout
        )
        response.raise_for_status()
        attributes = {
            str(record["name"]): str(record.get("type") or "")
            for record in _extract_records(response.json())
            if record.get("name")
        }
        logger.info("Program %d has %d registration attributes", program_id, len(attributes))
        return attributes

    def create_registration_attribute(
        self, program_id: int, payload: dict[str, object]
    ) -> requests.Response:
        """Create one registration attribute; the endpoint takes a single object."""
        self._ensure_login()
        return self.session.post(
            f"{self.base_url}/api/programs/{program_id}/registration-attributes",
            json=payload,
            timeout=self.timeout,
        )

    def create_registrations(
        self, program_id: int, payload: list[dict[str, Scalar]]
    ) -> requests.Response:
        """Create registrations in a single batched request."""
        self._ensure_login()
        return self.session.post(
            f"{self.base_url}/api/programs/{program_id}/registrations",
            json=payload,
            timeout=self.timeout,
        )

    def _ensure_login(self) -> None:
        if not self._logged_in:
            self.login()


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    """Unwrap the paginated `{"data": [...]}` envelope used by 121 list endpoints."""
    records = payload.get("data", []) if isinstance(payload, dict) else payload
    return [record for record in records if isinstance(record, dict)]

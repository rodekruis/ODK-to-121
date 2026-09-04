"""ODK Central client (session auth + OData submissions feed)."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

import requests

from odk_to_121.infra.utils.http import DEFAULT_TIMEOUT, create_resilient_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 500


class OdkClientError(RuntimeError):
    """Raised when ODK Central cannot be reached or authenticated against."""


class OdkClient:
    """Reads submissions from ODK Central. One instance per run."""

    def __init__(
        self, base_url: str, username: str, password: str, *, timeout: int = DEFAULT_TIMEOUT
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self.timeout = timeout
        self.session = create_resilient_session()
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> OdkClient:
        base_url = os.environ.get("ODK_BASE_URL")
        username = os.environ.get("ODK_USERNAME")
        password = os.environ.get("ODK_PASSWORD")
        if not (base_url and username and password):
            raise OdkClientError("Missing ODK_BASE_URL, ODK_USERNAME or ODK_PASSWORD")
        return cls(base_url, username, password)

    def login(self) -> None:
        """Exchange credentials for a session token."""
        response = self.session.post(
            f"{self.base_url}/v1/sessions",
            json={"email": self._username, "password": self._password},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise OdkClientError(f"ODK login failed with status {response.status_code}")
        token = response.json().get("token")
        if not token:
            raise OdkClientError("ODK login response contained no token")
        self._token = token
        logger.info("Authenticated against ODK Central at %s", self.base_url)

    def get_submissions(
        self, project_id: int, form_id: str, *, submission_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all submission rows of a form via OData, following pagination."""
        if self._token is None:
            self.login()

        url = (
            f"{self.base_url}/v1/projects/{project_id}"
            f"/forms/{quote(form_id, safe='')}.svc/Submissions"
        )
        params: dict[str, str | int] = {"$top": PAGE_SIZE, "$skip": 0, "$expand": "*"}
        if submission_filter:
            params["$filter"] = submission_filter

        rows: list[dict[str, Any]] = []
        while True:
            payload = self._get_json(url, params)
            batch = payload.get("value", [])
            if not isinstance(batch, list):
                raise OdkClientError(f"Unexpected OData payload for form '{form_id}'")
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            params["$skip"] = int(params["$skip"]) + PAGE_SIZE

        logger.info("Fetched %d submissions from form '%s'", len(rows), form_id)
        return rows

    def _get_json(self, url: str, params: dict[str, str | int]) -> dict[str, Any]:
        try:
            response = self.session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise OdkClientError(f"ODK request to {url} failed: {exc}") from exc

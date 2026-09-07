"""Write-only abstraction over output targets: accumulate, validate, then load."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import requests

from odk_to_121.data_types.config_types import OutputMode
from odk_to_121.data_types.domain_types import Scalar
from odk_to_121.data_types.output_types import Registration, RegistrationBatch
from odk_to_121.utils.client_121 import Client121
from odk_to_121.utils.integrity_checks import check_batch

logger = logging.getLogger(__name__)


class DataSubmitter:
    """Builder that domain code fills, and that owns validation and loading."""

    def __init__(
        self,
        route_id: str,
        program_id: int,
        source_form_id: str,
        *,
        fsp_configuration_name: str | None = None,
        issued_at: datetime | None = None,
        client_121: Client121 | None = None,
    ):
        """Open an empty batch for one route; without a 121 client only local output works."""
        self.route_id = route_id
        self.client_121 = client_121
        self.fsp_configuration_name = fsp_configuration_name
        self._batch = RegistrationBatch(
            program_id=program_id,
            issued_at=issued_at or datetime.now(UTC),
            source_form_id=source_form_id,
        )

    @property
    def registrations(self) -> list[Registration]:
        """Everything accumulated so far, for logging and assertions."""
        return self._batch.registrations

    def create_registration(
        self,
        reference_id: str,
        attributes: dict[str, Scalar],
        preferred_language: str | None = None,
    ) -> None:
        """Called by domain code to build output incrementally."""
        self._batch.registrations.append(
            Registration(
                reference_id=reference_id,
                attributes=attributes,
                preferred_language=preferred_language,
                fsp_configuration_name=self.fsp_configuration_name,
            )
        )

    def validate(self) -> list[str]:
        """Run every integrity check without loading anything. Empty list = safe to load."""
        return check_batch(self.route_id, self._batch)

    def load_all(
        self,
        output_mode: OutputMode,
        output_path: str,
    ) -> list[str]:
        """Validate everything, then load. All-or-nothing."""
        errors = self.validate()
        if errors:
            logger.error("%s: integrity checks failed (%d)", self.route_id, len(errors))
            return errors

        if not self._batch.registrations:
            logger.info("%s: nothing to submit", self.route_id)
            return []

        match output_mode:
            case OutputMode.LOCAL:
                return self._load_to_file(output_path)
            case OutputMode.PLATFORM_121:
                return self._load_to_121()

    def _load_to_file(self, output_path: str) -> list[str]:
        """Load the batch into a timestamped directory, atomically."""
        stamp = self._batch.issued_at.strftime("%Y%m%dT%H%M%SZ")
        directory = Path(output_path) / self.route_id / stamp
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "registrations.json"

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=directory, encoding="utf-8"
            ) as tmp:
                json.dump(self._batch.to_dict(), tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, target)
        except OSError as exc:
            return [f"{self.route_id}: could not write output to {target}: {exc}"]

        logger.info(
            "%s: loaded %d registrations into %s",
            self.route_id,
            len(self.registrations),
            target,
        )
        return []

    def _load_to_121(self) -> list[str]:
        """Create the registrations 121 does not have yet; existing ones are left untouched."""
        client = self.client_121
        if client is None:
            return [f"{self.route_id}: no 121 client configured for API output"]

        try:
            existing = client.get_reference_ids(self._batch.program_id)
        except (requests.RequestException, ValueError) as exc:
            return [f"{self.route_id}: could not list existing registrations: {exc}"]

        to_create = [r for r in self.registrations if r.reference_id not in existing]
        skipped = len(self.registrations) - len(to_create)
        if skipped:
            logger.info("%s: skipped %d registrations already in 121", self.route_id, skipped)
        return self._create(client, to_create)

    def _create(self, client: Client121, registrations: list[Registration]) -> list[str]:
        """POST the whole batch in one request; 121 accepts or rejects it as a unit."""
        if not registrations:
            return []
        payload = [registration.to_dict() for registration in registrations]
        try:
            response = client.create_registrations(self._batch.program_id, payload)
        except requests.RequestException as exc:
            return [f"{self.route_id}: creating registrations failed: {exc}"]

        if response.status_code not in range(200, 300):
            return [
                f"{self.route_id}: 121 returned {response.status_code} on create: "
                f"{_redacted_body(response)}"
            ]
        logger.info("%s: created %d registrations", self.route_id, len(registrations))
        return []


def _redacted_body(response: requests.Response) -> str:
    """121 echoes the rejected answer back per row, which must never reach a log."""
    try:
        payload = response.json()
    except ValueError:
        return f"<{len(response.content)} byte non-JSON body>"
    return json.dumps(_strip_values(payload))[:500]


def _strip_values(payload: object) -> object:
    """Replace every 'value' entry, the only place 121 puts submitted data."""
    if isinstance(payload, dict):
        return {
            key: "[redacted]" if key == "value" else _strip_values(item)
            for key, item in payload.items()
        }
    if isinstance(payload, list):
        return [_strip_values(item) for item in payload]
    return payload

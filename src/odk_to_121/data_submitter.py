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
from odk_to_121.data_types.output_types import Registration
from odk_to_121.utils.client_121 import Client121
from odk_to_121.utils.integrity_checks import check_registrations
from odk_to_121.utils.progress import with_progress

logger = logging.getLogger(__name__)


class DataSubmitter:
    """Builder that domain code fills, and that owns validation and loading."""

    def __init__(
        self,
        route_id: str,
        program_id: int,
        source_form_id: str,
        *,
        default_fsp_configuration_name: str | None = None,
        known_fsp_configuration_names: frozenset[str] = frozenset(),
        issued_at: datetime | None = None,
        client_121: Client121 | None = None,
    ):
        """Open an empty run for one route; without a 121 client only local output works."""
        self.route_id = route_id
        self.program_id = program_id
        self.source_form_id = source_form_id
        self.issued_at = issued_at or datetime.now(UTC)
        self.client_121 = client_121
        self.default_fsp_configuration_name = default_fsp_configuration_name
        self.known_fsp_configuration_names = known_fsp_configuration_names
        self.registrations: list[Registration] = []

    def create_registration(
        self,
        reference_id: str,
        attributes: dict[str, Scalar],
        preferred_language: str | None = None,
        fsp_configuration_name: str | None = None,
    ) -> None:
        """Called by domain code to build output incrementally."""
        self.registrations.append(
            Registration(
                reference_id=reference_id,
                attributes=attributes,
                preferred_language=preferred_language,
                # The route default applies unless the ODK form named one for this person.
                fsp_configuration_name=fsp_configuration_name
                or self.default_fsp_configuration_name,
            )
        )

    def validate(self) -> list[str]:
        """Run every integrity check without loading anything. Empty list = all are loadable."""
        _, errors = self._check()
        return errors

    def load_all(
        self,
        output_mode: OutputMode,
        output_path: str,
    ) -> list[str]:
        """Load every registration that passes its checks; the rest are reported and skipped."""
        loadable, errors = self._check()

        if not loadable:
            logger.info("%s: nothing to load", self.route_id)
            return errors

        match output_mode:
            case OutputMode.LOCAL:
                return errors + self._load_to_file(loadable, output_path)
            case OutputMode.PLATFORM_121:
                return errors + self._load_to_121(loadable)

    def _check(self) -> tuple[list[Registration], list[str]]:
        """Partition the run, logging how much of it is being held back."""
        loadable, errors = check_registrations(
            self.route_id, self.registrations, self.known_fsp_configuration_names
        )
        quarantined = len(self.registrations) - len(loadable)
        if quarantined:
            logger.error(
                "%s: %d of %d registrations failed integrity checks and will not be loaded",
                self.route_id,
                quarantined,
                len(self.registrations),
                extra={"route_id": self.route_id, "quarantined": quarantined},
            )
            for error in errors:
                logger.error("%s", error)
        return loadable, errors

    def _load_to_file(self, registrations: list[Registration], output_path: str) -> list[str]:
        """Load the run into a timestamped directory, atomically."""
        stamp = self.issued_at.strftime("%Y%m%dT%H%M%SZ")
        directory = Path(output_path) / self.route_id / stamp
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "registrations.json"

        payload = {
            "programId": self.program_id,
            "issuedAt": self.issued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sourceFormId": self.source_form_id,
            "registrations": [registration.to_dict() for registration in registrations],
        }
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=directory, encoding="utf-8"
            ) as tmp:
                json.dump(payload, tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, target)
        except OSError as exc:
            return [f"{self.route_id}: could not write output to {target}: {exc}"]

        logger.info(
            "%s: loaded %d registrations into %s",
            self.route_id,
            len(registrations),
            target,
        )
        return []

    def _load_to_121(self, registrations: list[Registration]) -> list[str]:
        """Create the registrations 121 does not have yet; existing ones are left untouched."""
        client = self.client_121
        if client is None:
            return [f"{self.route_id}: no 121 client configured for API output"]

        try:
            existing = client.get_reference_ids(self.program_id)
        except (requests.RequestException, ValueError) as exc:
            return [f"{self.route_id}: could not list existing registrations: {exc}"]

        to_create = [r for r in registrations if r.reference_id not in existing]
        skipped = len(registrations) - len(to_create)
        if skipped:
            logger.info("%s: skipped %d registrations already in 121", self.route_id, skipped)
        return self._create(client, to_create)

    def _create(self, client: Client121, registrations: list[Registration]) -> list[str]:
        """One request per registration, so one rejection never holds back the others."""
        errors: list[str] = []
        progress = with_progress(registrations, f"{self.route_id}: creating registrations", "reg")
        for registration in progress:
            error = self._create_one(client, registration)
            if error:
                logger.error("%s", error, extra={"route_id": self.route_id})
                errors.append(error)

        created = len(registrations) - len(errors)
        logger.info(
            "%s: created %d of %d registrations",
            self.route_id,
            created,
            len(registrations),
            extra={"route_id": self.route_id, "created_count": created, "failed": len(errors)},
        )
        return errors

    def _create_one(self, client: Client121, registration: Registration) -> str | None:
        """Return why this one registration could not be created, or None if it was."""
        subject = f"{self.route_id}: registration {registration.reference_id}"
        try:
            response = client.create_registration(self.program_id, registration.to_dict())
        except requests.RequestException as exc:
            return f"{subject} could not be created: {exc}"

        if response.status_code not in range(200, 300):
            return f"{subject} was rejected with {response.status_code}: {_redacted_body(response)}"
        return None


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

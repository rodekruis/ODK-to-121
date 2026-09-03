"""Output payloads. Schema must stay in sync with the 121 registration DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from odk_to_121.infra.data_types.domain_types import Scalar


@dataclass
class Registration:
    """One 121 registration, keyed by a deterministic reference id."""

    reference_id: str
    attributes: dict[str, Scalar] = field(default_factory=dict)
    preferred_language: str | None = None

    def to_dict(self) -> dict[str, Scalar]:
        payload: dict[str, Scalar] = {"referenceId": self.reference_id}
        if self.preferred_language:
            payload["preferredLanguage"] = self.preferred_language
        payload.update(self.attributes)
        return payload


@dataclass
class RegistrationBatch:
    """All registrations produced for one entity in one run."""

    program_id: int
    issued_at: datetime
    source_form_id: str
    registrations: list[Registration] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "programId": self.program_id,
            "issuedAt": self.issued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sourceFormId": self.source_form_id,
            "registrations": [r.to_dict() for r in self.registrations],
        }

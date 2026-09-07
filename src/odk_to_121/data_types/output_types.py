"""Output payloads. Schema must stay in sync with the 121 registration DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from odk_to_121.data_types.domain_types import Scalar


class AttributeType(StrEnum):
    """The attribute types `CreateProgramRegistrationAttributeDto` accepts."""

    TEXT = "text"
    NUMERIC = "numeric"
    TEL = "tel"
    DATE = "date"
    DROPDOWN = "dropdown"


@dataclass(frozen=True)
class ProgramAttribute:
    """One 121 program registration attribute to create."""

    name: str
    type: AttributeType

    def to_dict(self) -> dict[str, object]:
        """Serialize for 121's create-attribute endpoint."""
        return {
            "name": self.name,
            # ODK's fields endpoint carries no question labels, so the field name is
            # used as the label -- 121's own fallback for unlabelled questions.
            "label": {"en": self.name},
            "type": self.type.value,
            # ODK 'required' is conditional on skip logic, so it is never mirrored here.
            "isRequired": False,
            "showInPeopleAffectedTable": True,
            "editableInPortal": True,
        }


@dataclass(frozen=True)
class ExistingAttribute:
    """One registration attribute a 121 program already has."""

    name: str
    # Kept as a string: 121 has attribute types this pipeline never creates.
    type: str
    is_required: bool = False

    @classmethod
    def from_121(cls, raw: dict[str, Any]) -> ExistingAttribute:
        """Parse one entry of 121's program attributes response."""
        name = str(raw.get("name") or "")
        if not name:
            raise ValueError(f"registration attribute is missing 'name': {sorted(raw)}")
        return cls(
            name=name,
            type=str(raw.get("type") or ""),
            is_required=bool(raw.get("isRequired")),
        )


@dataclass(frozen=True)
class ExistingProgram:
    """The 121 program a route loads into."""

    # Attribute names 121 concatenates into a registration's displayed name.
    fullname_naming_convention: tuple[str, ...] = ()

    @classmethod
    def from_121(cls, raw: dict[str, Any]) -> ExistingProgram:
        """Parse 121's program response, keeping only what the pipeline acts on."""
        convention = raw.get("fullnameNamingConvention") or []
        if not isinstance(convention, list):
            raise ValueError(f"'fullnameNamingConvention' is not a list: {convention!r}")
        return cls(fullname_naming_convention=tuple(str(name) for name in convention))


@dataclass
class Registration:
    """One 121 registration, keyed by a deterministic reference id."""

    reference_id: str
    attributes: dict[str, Scalar] = field(default_factory=dict)
    preferred_language: str | None = None
    fsp_configuration_name: str | None = None

    def to_dict(self) -> dict[str, Scalar]:
        """Serialize for 121's create-registrations endpoint."""
        payload: dict[str, Scalar] = {"referenceId": self.reference_id}
        if self.preferred_language:
            payload["preferredLanguage"] = self.preferred_language
        if self.fsp_configuration_name:
            payload["programFspConfigurationName"] = self.fsp_configuration_name
        payload.update(self.attributes)
        return payload


@dataclass
class RegistrationBatch:
    """All registrations produced for one route in one run."""

    program_id: int
    issued_at: datetime
    source_form_id: str
    registrations: list[Registration] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize for local output; the run metadata is not sent to 121."""
        return {
            "programId": self.program_id,
            "issuedAt": self.issued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sourceFormId": self.source_form_id,
            "registrations": [r.to_dict() for r in self.registrations],
        }

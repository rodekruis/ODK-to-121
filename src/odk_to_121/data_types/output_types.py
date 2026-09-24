"""Output payloads. Schema must stay in sync with the 121 registration DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from odk_to_121.data_types.domain_types import Scalar, Translations

# Keys of 121's registration DTO that `Registration` carries as fields of its own.
PREFERRED_LANGUAGE_ATTRIBUTE = "preferredLanguage"
FSP_CONFIGURATION_ATTRIBUTE = "programFspConfigurationName"

# 121 keys its own fallbacks on English, and the portal reads it when a label is missing.
FALLBACK_LANGUAGE = "en"


class AttributeType(StrEnum):
    """The attribute types `CreateProgramRegistrationAttributeDto` accepts."""

    TEXT = "text"
    NUMERIC = "numeric"
    TEL = "tel"
    DATE = "date"
    DROPDOWN = "dropdown"


@dataclass(frozen=True)
class AttributeOption:
    """One selectable value of a 121 dropdown attribute."""

    option: str
    labels: Translations = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize for 121's attribute endpoints."""
        return {"option": self.option, "label": _with_fallback(self.labels, self.option)}


@dataclass(frozen=True)
class ProgramAttribute:
    """One 121 program registration attribute to create."""

    name: str
    type: AttributeType
    labels: Translations = field(default_factory=dict)
    options: tuple[AttributeOption, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize for 121's create-attribute endpoint."""
        payload: dict[str, object] = {
            "name": self.name,
            "label": _with_fallback(self.labels, self.name),
            "type": self.type.value,
            # ODK 'required' is conditional on skip logic, so it is never mirrored here.
            "isRequired": False,
            "showInPeopleAffectedTable": True,
            "editableInPortal": True,
        }
        if self.type is AttributeType.DROPDOWN:
            payload["options"] = [option.to_dict() for option in self.options]
        return payload


def _with_fallback(labels: Translations, name: str) -> dict[str, str]:
    """An unlabelled question falls back to its own name, which is what 121 does for Kobo."""
    return dict(labels) if FALLBACK_LANGUAGE in labels else {FALLBACK_LANGUAGE: name, **labels}


@dataclass(frozen=True)
class ExistingAttribute:
    """One registration attribute a 121 program already has."""

    name: str
    # Kept as a string: 121 has attribute types this pipeline never creates.
    type: str
    is_required: bool = False
    # Only dropdowns have these; the values 121 will accept for this attribute.
    options: tuple[str, ...] = ()

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
            options=_parse_options(raw.get("options")),
        )


def _parse_options(raw: Any) -> tuple[str, ...]:
    """Keep the option codes only; they are all the pipeline needs to spot a drifted list."""
    if not isinstance(raw, list):
        return ()
    return tuple(
        str(entry["option"])
        for entry in raw
        if isinstance(entry, dict) and entry.get("option") is not None
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
        payload: dict[str, Scalar] = dict(self.attributes)
        payload["referenceId"] = self.reference_id
        if self.preferred_language:
            payload[PREFERRED_LANGUAGE_ATTRIBUTE] = self.preferred_language
        if self.fsp_configuration_name:
            payload[FSP_CONFIGURATION_ATTRIBUTE] = self.fsp_configuration_name
        return payload

"""Domain data structures: ODK submissions and the mapping contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Scalar values accepted as ODK answers and as 121 registration attributes.
type Scalar = str | int | float | bool | None

ODK_SYSTEM_KEY = "__system"
ODK_INSTANCE_ID_KEY = "__id"


@dataclass(frozen=True)
class OdkSubmission:
    """A single ODK submission with its answers flattened to `group/field` keys."""

    instance_id: str
    submission_date: datetime | None
    review_state: str | None
    values: dict[str, Scalar] = field(default_factory=dict)

    @classmethod
    def from_odata(cls, raw: dict[str, Any]) -> OdkSubmission:
        """Parse one row of an ODK Central OData `Submissions` feed."""
        instance_id = raw.get(ODK_INSTANCE_ID_KEY)
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError(f"submission is missing '{ODK_INSTANCE_ID_KEY}': {sorted(raw)}")

        system = raw.get(ODK_SYSTEM_KEY) or {}
        submitted_raw = system.get("submissionDate")
        review_state = system.get("reviewState")

        answers = {k: v for k, v in raw.items() if not k.startswith("__")}
        return cls(
            instance_id=instance_id,
            submission_date=_parse_timestamp(submitted_raw),
            review_state=review_state if isinstance(review_state, str) else None,
            values=_flatten(answers),
        )

    def get(self, path: str) -> Scalar:
        """Read an answer by its flattened `group/field` path."""
        if path == ODK_INSTANCE_ID_KEY:
            return self.instance_id
        return self.values.get(path)


@dataclass(frozen=True)
class OdkSubmissionSet:
    """All submissions fetched for one ODK form."""

    project_id: int
    form_id: str
    submissions: tuple[OdkSubmission, ...] = ()

    def __len__(self) -> int:
        return len(self.submissions)


@dataclass(frozen=True)
class OdkFormField:
    """One field of an ODK form schema, from the Central `/fields` endpoint."""

    name: str
    path: str
    type: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> OdkFormField:
        # Paths arrive as '/group/field'; submissions flatten to 'group/field'.
        path = str(raw.get("path") or "").lstrip("/")
        name = str(raw.get("name") or "")
        if not path or not name:
            raise ValueError(f"form field is missing 'name' or 'path': {sorted(raw)}")
        return cls(name=name, path=path, type=str(raw.get("type") or "unknown"))


@dataclass(frozen=True)
class OdkFormSchema:
    """The flat field schema of one ODK form."""

    project_id: int
    form_id: str
    fields: tuple[OdkFormField, ...] = ()


@dataclass(frozen=True)
class FieldMapping:
    """Maps one flattened ODK field onto one 121 registration attribute."""

    odk_field: str
    attribute: str
    required: bool = False


@dataclass(frozen=True)
class RegistrationMapping:
    """Everything the transform needs, built by infra from config."""

    program_id: int
    reference_id_field: str
    fields: tuple[FieldMapping, ...]
    preferred_language: str | None = None


def _flatten(values: dict[str, Any], prefix: str = "") -> dict[str, Scalar]:
    """Flatten nested ODK groups into `group/field` keys; repeats stay as-is."""
    flat: dict[str, Scalar] = {}
    for key, value in values.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, prefix=f"{path}/"))
        elif isinstance(value, list):
            flat[path] = len(value)  # repeat groups are not supported yet
        else:
            flat[path] = value
    return flat


def _parse_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

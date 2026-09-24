"""Domain data structures: ODK submissions and the mapping contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Scalar values accepted as ODK answers and as 121 registration attributes.
type Scalar = str | int | float | bool | None

# Question labels and choice labels, keyed by ISO 639-1 language code.
type Translations = dict[str, str]

ODK_INSTANCE_ID_KEY = "__id"


@dataclass(frozen=True)
class OdkSubmission:
    """A single ODK submission with its answers flattened to `group/field` keys."""

    instance_id: str
    values: dict[str, Scalar] = field(default_factory=dict)

    @classmethod
    def from_odata(cls, raw: dict[str, Any]) -> OdkSubmission:
        """Parse one row of an ODK Central OData `Submissions` feed."""
        instance_id = raw.get(ODK_INSTANCE_ID_KEY)
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError(f"submission is missing '{ODK_INSTANCE_ID_KEY}': {sorted(raw)}")

        # Everything ODK prefixes with '__' is system metadata, not an answer.
        answers = {k: v for k, v in raw.items() if not k.startswith("__")}
        return cls(instance_id=instance_id, values=_flatten(answers))

    def get(self, path: str) -> Scalar:
        """Read an answer by its flattened `group/field` path."""
        return self.values.get(path)


@dataclass(frozen=True)
class OdkSubmissionSet:
    """All submissions fetched for one ODK form."""

    project_id: int
    form_id: str
    submissions: tuple[OdkSubmission, ...] = ()

    def __len__(self) -> int:
        """Number of submissions, so callers can treat the set as a collection."""
        return len(self.submissions)


@dataclass(frozen=True)
class OdkFormField:
    """One field of an ODK form schema, from the Central `/fields` endpoint."""

    name: str
    path: str
    type: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> OdkFormField:
        """Parse one entry of ODK Central's form `/fields` response."""
        # Paths arrive as '/group/field'; submissions flatten to 'group/field'.
        path = str(raw.get("path") or "").lstrip("/")
        name = str(raw.get("name") or "")
        if not path or not name:
            raise ValueError(f"form field is missing 'name' or 'path': {sorted(raw)}")
        return cls(name=name, path=path, type=str(raw.get("type") or "unknown"))


class SelectKind(StrEnum):
    """How many answers an ODK select question accepts."""

    ONE = "select_one"
    MULTIPLE = "select_multiple"


@dataclass(frozen=True)
class OdkChoice:
    """One option of an ODK select question."""

    value: str
    labels: Translations = field(default_factory=dict)


@dataclass(frozen=True)
class OdkQuestion:
    """One question of an ODK form, as the XForms definition describes it.

    Carries what the `/fields` endpoint cannot: labels, and whether the question is a
    select plus the choices it offers.
    """

    path: str
    labels: Translations = field(default_factory=dict)
    select_kind: SelectKind | None = None
    choices: tuple[OdkChoice, ...] = ()


@dataclass(frozen=True)
class OdkFormDefinition:
    """The questions of one ODK form, keyed by the same path the `/fields` endpoint uses."""

    questions: dict[str, OdkQuestion] = field(default_factory=dict)

    def get(self, path: str) -> OdkQuestion | None:
        """Read a question by its `/group/field` path."""
        return self.questions.get(path)


@dataclass(frozen=True)
class OdkFormSchema:
    """The flat field schema of one ODK form."""

    project_id: int
    form_id: str
    fields: tuple[OdkFormField, ...] = ()
    definition: OdkFormDefinition = field(default_factory=OdkFormDefinition)


@dataclass(frozen=True)
class FieldMapping:
    """Maps one flattened ODK field onto one 121 registration attribute."""

    odk_field: str
    attribute: str
    is_built_in: bool = False


@dataclass(frozen=True)
class RegistrationMapping:
    """Everything the transform needs, built from config and the synced schema."""

    fields: tuple[FieldMapping, ...]


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

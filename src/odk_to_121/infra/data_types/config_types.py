"""Config enums and frozen config dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from odk_to_121.infra.data_types.domain_types import FieldMapping


class RunTarget(StrEnum):
    DEBUG = "debug"
    TEST = "test"
    PROD = "prod"


class PipelineType(StrEnum):
    REGISTRATIONS = "registrations"


class DataSource(StrEnum):
    ODK_SUBMISSIONS = "odk_submissions"
    DUMMY_SUBMISSIONS = "dummy_submissions"


class OutputMode(StrEnum):
    LOCAL = "local"
    API = "api"


class SubmissionMode(StrEnum):
    CREATE = "create"
    UPSERT = "upsert"


@dataclass(frozen=True)
class OdkFormConfig:
    project_id: int
    form_id: str
    submission_filter: str | None = None  # OData $filter, e.g. on __system/submissionDate


@dataclass(frozen=True)
class ProgramConfig:
    program_id: int
    submission_mode: SubmissionMode = SubmissionMode.UPSERT
    preferred_language: str | None = None


@dataclass(frozen=True)
class EntityRunConfig:
    """One ODK form -> one 121 program."""

    entity_id: str
    data_source: DataSource
    odk: OdkFormConfig
    program: ProgramConfig
    field_mappings: tuple[FieldMapping, ...]
    output_mode: OutputMode
    output_path: str
    reference_id_field: str = "__id"
    skip_review_states: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineRunConfig:
    run_target: RunTarget
    pipeline_type: PipelineType
    entities: dict[str, EntityRunConfig]

"""Config enums and frozen config dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Environment(StrEnum):
    DEBUG = "debug"
    TEST = "test"
    PROD = "prod"


class DataSource(StrEnum):
    ODK_SUBMISSIONS = "odk_submissions"
    DUMMY_SUBMISSIONS = "dummy_submissions"


class OutputMode(StrEnum):
    LOCAL = "local"
    PLATFORM_121 = "121"


@dataclass(frozen=True)
class OdkFormConfig:
    project_id: int
    form_id: str


@dataclass(frozen=True)
class ProgramConfig:
    program_id: int
    preferred_language: str | None = None


@dataclass(frozen=True)
class RunTargetConfig:
    """One ODK form -> one 121 program."""

    run_target_id: str
    data_source: DataSource
    odk: OdkFormConfig
    program: ProgramConfig
    output_mode: OutputMode
    output_path: str
    # Attributes a registration cannot be submitted without. Not derived from ODK's
    # 'required' bind, which stays true even when skip logic makes a question irrelevant.
    required_attributes: tuple[str, ...] = ()
    reference_id_field: str = "__id"


@dataclass(frozen=True)
class PipelineRunConfig:
    environment: Environment
    run_targets: dict[str, RunTargetConfig]

"""Config enums and frozen config dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Environment(StrEnum):
    """Which set of routes to run: dummy data, the 121 test instance, or production."""

    DEBUG = "debug"
    TEST = "test"
    PROD = "prod"


class DataSource(StrEnum):
    """Where a route's submissions come from."""

    ODK_SUBMISSIONS = "odk_submissions"
    DUMMY_SUBMISSIONS = "dummy_submissions"


class OutputMode(StrEnum):
    """Where a route's registrations go."""

    LOCAL = "local"
    PLATFORM_121 = "121"


@dataclass(frozen=True)
class OdkFormConfig:
    """The ODK Central form a route extracts from."""

    project_id: int
    form_id: str


@dataclass(frozen=True)
class ProgramConfig:
    """The 121 program a route loads into."""

    program_id: int


@dataclass(frozen=True)
class RouteConfig:
    """One ODK form -> one 121 program."""

    route_id: str
    data_source: DataSource
    odk: OdkFormConfig
    program: ProgramConfig
    output_mode: OutputMode
    output_path: str


@dataclass(frozen=True)
class PipelineRunConfig:
    """Every route to run for one environment, keyed by route id."""

    environment: Environment
    routes: dict[str, RouteConfig]

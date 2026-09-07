"""Load and validate the YAML pipeline config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from odk_to_121.data_types.config_types import (
    DataSource,
    Environment,
    OdkFormConfig,
    OutputMode,
    PipelineRunConfig,
    ProgramConfig,
    RouteConfig,
)

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when the config is missing or invalid."""


class ConfigReader:
    """Parses config into frozen dataclasses. Returns False on any validation error."""

    def __init__(self) -> None:
        """Start empty; `load` fills one run config per environment found in the YAML."""
        self.run_configs: dict[Environment, PipelineRunConfig] = {}

    def load(self, path: Path) -> bool:
        """Read and validate the YAML file. Logs the first problem and returns False."""
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            logger.error("Cannot read config %s: %s", path, exc)
            return False

        if not isinstance(raw, dict):
            logger.error("Config %s: expected a mapping at the top level", path)
            return False

        environments = raw.get("environments")
        if not isinstance(environments, dict) or not environments:
            logger.error("Config %s: 'environments' must be a non-empty mapping", path)
            return False

        for name, body in environments.items():
            try:
                environment = Environment(name)
            except ValueError:
                logger.error(
                    "Config %s: unknown environment '%s', expected one of %s",
                    path,
                    name,
                    [e.value for e in Environment],
                )
                return False

            routes = self._parse_routes(body, environment)
            if routes is None:
                return False
            self.run_configs[environment] = PipelineRunConfig(
                environment=environment,
                routes=routes,
            )

        logger.info("Loaded config %s with environments %s", path, sorted(self.run_configs))
        return True

    def get_run_config(self, environment: Environment) -> PipelineRunConfig:
        """Return the routes to run for one environment, or raise if it is undefined."""
        if environment not in self.run_configs:
            raise ConfigError(f"Environment '{environment}' is not defined in the config")
        return self.run_configs[environment]

    def _parse_routes(self, body: Any, environment: Environment) -> dict[str, RouteConfig] | None:
        """Parse one environment's routes, keyed by route id, rejecting duplicates."""
        if not isinstance(body, dict) or not isinstance(body.get("routes"), list):
            logger.error("Environment '%s': 'routes' must be a list", environment)
            return None

        routes: dict[str, RouteConfig] = {}
        for raw_route in body["routes"]:
            route = self._parse_route(raw_route, environment)
            if route is None:
                return None
            if route.route_id in routes:
                logger.error(
                    "Environment '%s': duplicate route id '%s'",
                    environment,
                    route.route_id,
                )
                return None
            routes[route.route_id] = route

        if not routes:
            logger.error("Environment '%s': no routes defined", environment)
            return None
        return routes

    def _parse_route(self, raw: Any, environment: Environment) -> RouteConfig | None:
        """Turn one YAML route mapping into a RouteConfig, logging why it was rejected."""
        if not isinstance(raw, dict) or not raw.get("id"):
            logger.error("Environment '%s': every route needs an 'id'", environment)
            return None
        route_id = str(raw["id"])

        try:
            data_source = DataSource(raw.get("data_source"))
            odk = _parse_odk(raw.get("odk"))
            # An unquoted `121:` key parses as an int, so accept the quoted form too.
            program = _parse_program(raw.get(121, raw.get("121")))
            output_mode, output_path = _parse_output(raw.get("output"))
            fsp_configuration_name = _parse_fsp_configuration_name(
                raw.get("fsp_configuration_name")
            )
        except (ValueError, TypeError, KeyError) as exc:
            logger.error("Environment '%s', route '%s': %s", environment, route_id, exc)
            return None

        return RouteConfig(
            route_id=route_id,
            data_source=data_source,
            odk=odk,
            program=program,
            output_mode=output_mode,
            output_path=output_path,
            fsp_configuration_name=fsp_configuration_name,
        )


def _parse_odk(raw: Any) -> OdkFormConfig:
    """Read the ODK Central project and form a route extracts from."""
    if not isinstance(raw, dict):
        raise TypeError("'odk' must be a mapping with project_id and form_id")
    return OdkFormConfig(
        project_id=int(raw["project_id"]),
        form_id=str(raw["form_id"]),
    )


def _parse_program(raw: Any) -> ProgramConfig:
    """Read the 121 program a route loads into."""
    if not isinstance(raw, dict):
        raise TypeError("'121' must be a mapping with program_id")
    program_id = int(raw["program_id"])
    if program_id <= 0:
        raise ValueError(f"program_id must be positive, got {program_id}")
    return ProgramConfig(program_id=program_id)


def _parse_output(raw: Any) -> tuple[OutputMode, str]:
    """Read where a route's registrations go: local files or the 121 API."""
    if not isinstance(raw, dict):
        raise TypeError("'output' must be a mapping with mode")
    # An unquoted `mode: 121` parses as an int.
    mode = OutputMode(str(raw["mode"]))
    path = str(raw.get("path", "output/"))
    if mode is OutputMode.LOCAL and not path:
        raise ValueError("output mode 'local' requires a path")
    return mode, path


def _parse_fsp_configuration_name(raw: Any) -> str:
    """Read the 121 FSP configuration every registration of a route is created under."""
    name = str(raw or "").strip()
    if not name:
        raise ValueError("'fsp_configuration_name' is required")
    return name

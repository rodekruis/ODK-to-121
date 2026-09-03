"""Load and validate the YAML pipeline config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from odk_to_121.infra.data_types.config_types import (
    DataSource,
    EntityRunConfig,
    OdkFormConfig,
    OutputMode,
    PipelineRunConfig,
    PipelineType,
    ProgramConfig,
    RunTarget,
    SubmissionMode,
)
from odk_to_121.infra.data_types.domain_types import FieldMapping

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when the config is missing or invalid."""


class ConfigReader:
    """Parses config into frozen dataclasses. Returns False on any validation error."""

    def __init__(self) -> None:
        self.pipeline_type: PipelineType | None = None
        self.run_configs: dict[RunTarget, PipelineRunConfig] = {}

    def load(self, path: Path) -> bool:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            logger.error("Cannot read config %s: %s", path, exc)
            return False

        if not isinstance(raw, dict):
            logger.error("Config %s: expected a mapping at the top level", path)
            return False

        try:
            self.pipeline_type = PipelineType(raw.get("pipeline_type"))
        except ValueError:
            logger.error(
                "Config %s: invalid pipeline_type, expected one of %s",
                path,
                [t.value for t in PipelineType],
            )
            return False

        run_targets = raw.get("run_targets")
        if not isinstance(run_targets, dict) or not run_targets:
            logger.error("Config %s: 'run_targets' must be a non-empty mapping", path)
            return False

        for name, body in run_targets.items():
            try:
                target = RunTarget(name)
            except ValueError:
                logger.error(
                    "Config %s: unknown run target '%s', expected one of %s",
                    path,
                    name,
                    [t.value for t in RunTarget],
                )
                return False

            entities = self._parse_entities(body, target)
            if entities is None:
                return False
            self.run_configs[target] = PipelineRunConfig(
                run_target=target, pipeline_type=self.pipeline_type, entities=entities
            )

        logger.info("Loaded config %s with run targets %s", path, sorted(self.run_configs))
        return True

    def get_run_config(self, target: RunTarget) -> PipelineRunConfig:
        if target not in self.run_configs:
            raise ConfigError(f"Run target '{target}' is not defined in the config")
        return self.run_configs[target]

    def _parse_entities(self, body: Any, target: RunTarget) -> dict[str, EntityRunConfig] | None:
        if not isinstance(body, dict) or not isinstance(body.get("entities"), list):
            logger.error("Run target '%s': 'entities' must be a list", target)
            return None

        entities: dict[str, EntityRunConfig] = {}
        for raw_entity in body["entities"]:
            entity = self._parse_entity(raw_entity, target)
            if entity is None:
                return None
            if entity.entity_id in entities:
                logger.error("Run target '%s': duplicate entity id '%s'", target, entity.entity_id)
                return None
            entities[entity.entity_id] = entity

        if not entities:
            logger.error("Run target '%s': no entities defined", target)
            return None
        return entities

    def _parse_entity(self, raw: Any, target: RunTarget) -> EntityRunConfig | None:
        if not isinstance(raw, dict) or not raw.get("id"):
            logger.error("Run target '%s': every entity needs an 'id'", target)
            return None
        entity_id = str(raw["id"])

        try:
            data_source = DataSource(raw.get("data_source"))
            odk = _parse_odk(raw.get("odk"))
            program = _parse_program(raw.get("program"))
            output_mode, output_path = _parse_output(raw.get("output"))
            field_mappings = _parse_field_mappings(raw.get("field_mappings"))
        except (ValueError, TypeError, KeyError) as exc:
            logger.error("Run target '%s', entity '%s': %s", target, entity_id, exc)
            return None

        return EntityRunConfig(
            entity_id=entity_id,
            data_source=data_source,
            odk=odk,
            program=program,
            field_mappings=field_mappings,
            output_mode=output_mode,
            output_path=output_path,
            reference_id_field=str(raw.get("reference_id_field", "__id")),
            skip_review_states=tuple(raw.get("skip_review_states", ())),
        )


def _parse_odk(raw: Any) -> OdkFormConfig:
    if not isinstance(raw, dict):
        raise TypeError("'odk' must be a mapping with project_id and form_id")
    return OdkFormConfig(
        project_id=int(raw["project_id"]),
        form_id=str(raw["form_id"]),
        submission_filter=raw.get("submission_filter"),
    )


def _parse_program(raw: Any) -> ProgramConfig:
    if not isinstance(raw, dict):
        raise TypeError("'program' must be a mapping with program_id")
    program_id = int(raw["program_id"])
    if program_id <= 0:
        raise ValueError(f"program_id must be positive, got {program_id}")
    return ProgramConfig(
        program_id=program_id,
        submission_mode=SubmissionMode(raw.get("submission_mode", SubmissionMode.UPSERT)),
        preferred_language=raw.get("preferred_language"),
    )


def _parse_output(raw: Any) -> tuple[OutputMode, str]:
    if not isinstance(raw, dict):
        raise TypeError("'output' must be a mapping with mode")
    mode = OutputMode(raw["mode"])
    path = str(raw.get("path", "output/"))
    if mode is OutputMode.LOCAL and not path:
        raise ValueError("output mode 'local' requires a path")
    return mode, path


def _parse_field_mappings(raw: Any) -> tuple[FieldMapping, ...]:
    if not isinstance(raw, list) or not raw:
        raise TypeError("'field_mappings' must be a non-empty list")

    mappings = []
    attributes: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or "odk_field" not in item or "attribute" not in item:
            raise TypeError(f"field mapping needs 'odk_field' and 'attribute': {item}")
        attribute = str(item["attribute"])
        if attribute in attributes:
            raise ValueError(f"attribute '{attribute}' is mapped more than once")
        attributes.add(attribute)
        mappings.append(
            FieldMapping(
                odk_field=str(item["odk_field"]),
                attribute=attribute,
                required=bool(item.get("required", False)),
                default=item.get("default"),
            )
        )
    return tuple(mappings)

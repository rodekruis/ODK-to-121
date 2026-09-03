"""Wires extract -> transform -> load per entity."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from odk_to_121.infra.config_reader import ConfigError, ConfigReader
from odk_to_121.infra.data_provider import DataProvider
from odk_to_121.infra.data_submitter import DataSubmitter
from odk_to_121.infra.data_types.config_types import (
    DataSource,
    EntityRunConfig,
    OutputMode,
    PipelineType,
    RunTarget,
)
from odk_to_121.infra.data_types.domain_types import RegistrationMapping
from odk_to_121.infra.utils.api_client import Api121Client
from odk_to_121.infra.utils.odk_client import OdkClient
from odk_to_121.registrations.transform import build_registrations

logger = logging.getLogger(__name__)

TransformFn = Callable[[DataProvider, DataSubmitter, str, RegistrationMapping], None]

TRANSFORM_FUNCTIONS: dict[PipelineType, TransformFn] = {
    PipelineType.REGISTRATIONS: build_registrations,
}


def run_pipeline(
    config_path: Path,
    run_target: RunTarget,
    *,
    issued_at: datetime | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Run the pipeline for every configured entity. Returns errors (empty = success)."""
    config = ConfigReader()
    if not config.load(config_path):
        raise ConfigError(f"Invalid configuration: {config_path}")

    run_config = config.get_run_config(run_target)
    transform_fn = TRANSFORM_FUNCTIONS[run_config.pipeline_type]

    odk_client = _build_odk_client(run_config.entities.values())
    api_client = _build_api_client(run_config.entities.values(), dry_run=dry_run)

    all_errors: list[str] = []
    for entity in run_config.entities.values():
        logger.info("Running entity '%s' (target=%s)", entity.entity_id, run_target)
        try:
            all_errors.extend(
                _run_entity(entity, transform_fn, odk_client, api_client, issued_at, dry_run)
            )
        except Exception as exc:  # noqa: BLE001 - one entity must not abort the run
            logger.exception("%s: unexpected failure", entity.entity_id)
            all_errors.append(f"{entity.entity_id}: unexpected failure: {exc}")

    return all_errors


def _run_entity(
    entity: EntityRunConfig,
    transform_fn: TransformFn,
    odk_client: OdkClient | None,
    api_client: Api121Client | None,
    issued_at: datetime | None,
    dry_run: bool,
) -> list[str]:
    provider = DataProvider(odk_client=odk_client)
    errors = provider.load_data(entity)
    if errors:
        return errors

    submitter = DataSubmitter(
        entity_id=entity.entity_id,
        program_id=entity.program.program_id,
        source_form_id=entity.odk.form_id,
        issued_at=issued_at,
        api_client=api_client,
    )
    transform_fn(provider, submitter, entity.entity_id, _build_mapping(entity))

    if dry_run:
        errors = submitter.validate(entity.field_mappings)
        logger.info(
            "%s: dry run, %d registrations validated, nothing sent",
            entity.entity_id,
            len(submitter.registrations),
        )
        return errors

    return submitter.send_all(
        entity.output_mode,
        entity.output_path,
        entity.field_mappings,
        entity.program.submission_mode,
    )


def _build_mapping(entity: EntityRunConfig) -> RegistrationMapping:
    """Translate config into the domain-facing mapping contract."""
    return RegistrationMapping(
        program_id=entity.program.program_id,
        reference_id_field=entity.reference_id_field,
        fields=entity.field_mappings,
        preferred_language=entity.program.preferred_language,
        skip_review_states=entity.skip_review_states,
    )


def _build_odk_client(entities: Iterable[EntityRunConfig]) -> OdkClient | None:
    needs_odk = any(e.data_source is DataSource.ODK_SUBMISSIONS for e in entities)
    return OdkClient.from_env() if needs_odk else None


def _build_api_client(entities: Iterable[EntityRunConfig], *, dry_run: bool) -> Api121Client | None:
    needs_api = any(e.output_mode is OutputMode.API for e in entities)
    return Api121Client.from_env() if needs_api and not dry_run else None

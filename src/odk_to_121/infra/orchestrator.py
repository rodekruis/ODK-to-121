"""Wires extract -> transform -> load per run target."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from odk_to_121.infra.config_reader import ConfigError, ConfigReader
from odk_to_121.infra.data_provider import DataProvider
from odk_to_121.infra.data_submitter import DataSubmitter
from odk_to_121.infra.data_types.config_types import (
    DataSource,
    Environment,
    OutputMode,
    RunTargetConfig,
)
from odk_to_121.infra.data_types.domain_types import RegistrationMapping
from odk_to_121.infra.schema_sync import SchemaPlan, sync_program_attributes
from odk_to_121.infra.utils.client_121 import Client121
from odk_to_121.infra.utils.client_odk import ClientOdk
from odk_to_121.transform import build_registrations

logger = logging.getLogger(__name__)


def run_pipeline(
    config_path: Path,
    environment: Environment,
    *,
    issued_at: datetime | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Run the pipeline for every run target of an environment. Returns errors (empty = ok)."""
    config = ConfigReader()
    if not config.load(config_path):
        raise ConfigError(f"Invalid configuration: {config_path}")

    run_config = config.get_run_config(environment)

    client_odk = _build_odk_client(run_config.run_targets.values())
    client_121 = _build_121_client(run_config.run_targets.values(), dry_run=dry_run)

    all_errors: list[str] = []
    for run_target in run_config.run_targets.values():
        logger.info("Running target '%s' (environment=%s)", run_target.run_target_id, environment)
        try:
            all_errors.extend(_run_target(run_target, client_odk, client_121, issued_at, dry_run))
        except Exception as exc:  # noqa: BLE001 - one target must not abort the run
            logger.exception("%s: unexpected failure", run_target.run_target_id)
            all_errors.append(f"{run_target.run_target_id}: unexpected failure: {exc}")

    return all_errors


def _run_target(
    run_target: RunTargetConfig,
    client_odk: ClientOdk | None,
    client_121: Client121 | None,
    issued_at: datetime | None,
    dry_run: bool,
) -> list[str]:
    provider = DataProvider(client_odk=client_odk)

    # 121 rejects attributes the program does not know, so the schema is reconciled first.
    plan, errors = sync_program_attributes(run_target, client_odk, client_121)
    if plan is None:
        return errors

    errors = provider.load_data(run_target)
    if errors:
        return errors

    submitter = DataSubmitter(
        run_target_id=run_target.run_target_id,
        program_id=run_target.program.program_id,
        source_form_id=run_target.odk.form_id,
        issued_at=issued_at,
        client_121=client_121,
    )
    build_registrations(
        provider, submitter, run_target.run_target_id, _build_mapping(run_target, plan)
    )

    if dry_run:
        errors = submitter.validate(plan.mappings)
        logger.info(
            "%s: dry run, %d registrations validated, nothing sent",
            run_target.run_target_id,
            len(submitter.registrations),
        )
        return errors

    return submitter.send_all(
        run_target.output_mode,
        run_target.output_path,
        plan.mappings,
    )


def _build_mapping(run_target: RunTargetConfig, plan: SchemaPlan) -> RegistrationMapping:
    """Translate config and the synced schema into the domain-facing mapping contract."""
    return RegistrationMapping(
        program_id=run_target.program.program_id,
        reference_id_field=run_target.reference_id_field,
        fields=plan.mappings,
        preferred_language=run_target.program.preferred_language,
    )


def _build_odk_client(run_targets: Iterable[RunTargetConfig]) -> ClientOdk | None:
    needs_odk = any(t.data_source is DataSource.ODK_SUBMISSIONS for t in run_targets)
    return ClientOdk.from_env() if needs_odk else None


def _build_121_client(run_targets: Iterable[RunTargetConfig], *, dry_run: bool) -> Client121 | None:
    needs_121 = any(t.output_mode is OutputMode.PLATFORM_121 for t in run_targets)
    return Client121.from_env() if needs_121 and not dry_run else None

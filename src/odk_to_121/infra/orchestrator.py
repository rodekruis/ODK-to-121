"""Wires extract -> transform -> load per route."""

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
    RouteConfig,
)
from odk_to_121.infra.data_types.domain_types import RegistrationMapping
from odk_to_121.infra.schema_sync import SchemaPlan, sync_program_attributes
from odk_to_121.infra.utils.client_121 import Client121
from odk_to_121.infra.utils.client_odk import ClientOdk
from odk_to_121.transform import transform_submissions

logger = logging.getLogger(__name__)


def run_pipeline(
    config_path: Path,
    environment: Environment,
    *,
    issued_at: datetime | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Run every route of an environment. Returns errors (empty = ok)."""
    config = ConfigReader()
    if not config.load(config_path):
        raise ConfigError(f"Invalid configuration: {config_path}")

    run_config = config.get_run_config(environment)

    client_odk = _build_client_odk(run_config.routes.values())
    client_121 = _build_client_121(run_config.routes.values(), dry_run=dry_run)

    all_errors: list[str] = []
    for route in run_config.routes.values():
        logger.info("Running route '%s' (environment=%s)", route.route_id, environment)
        try:
            all_errors.extend(_run_route(route, client_odk, client_121, issued_at, dry_run))
        except Exception as exc:  # noqa: BLE001 - one target must not abort the run
            logger.exception("%s: unexpected failure", route.route_id)
            all_errors.append(f"{route.route_id}: unexpected failure: {exc}")

    return all_errors


def _run_route(
    route: RouteConfig,
    client_odk: ClientOdk | None,
    client_121: Client121 | None,
    issued_at: datetime | None,
    dry_run: bool,
) -> list[str]:
    provider = DataProvider(client_odk=client_odk)

    # 121 rejects attributes the program does not know, so the schema is reconciled first.
    plan, errors = sync_program_attributes(route, client_odk, client_121)
    if plan is None:
        return errors

    errors = provider.extract_data(route)
    if errors:
        return errors

    submitter = DataSubmitter(
        route_id=route.route_id,
        program_id=route.program.program_id,
        source_form_id=route.odk.form_id,
        issued_at=issued_at,
        client_121=client_121,
    )
    transform_submissions(provider, submitter, route.route_id, _build_mapping(route, plan))

    if dry_run:
        errors = submitter.validate(plan.mappings)
        logger.info(
            "%s: dry run, %d registrations validated, nothing sent",
            route.route_id,
            len(submitter.registrations),
        )
        return errors

    return submitter.load_all(
        route.output_mode,
        route.output_path,
        plan.mappings,
    )


def _build_mapping(route: RouteConfig, plan: SchemaPlan) -> RegistrationMapping:
    """Translate config and the synced schema into the domain-facing mapping contract."""
    return RegistrationMapping(
        program_id=route.program.program_id,
        reference_id_field=route.reference_id_field,
        fields=plan.mappings,
        preferred_language=route.program.preferred_language,
    )


def _build_client_odk(routes: Iterable[RouteConfig]) -> ClientOdk | None:
    needs_odk = any(t.data_source is DataSource.ODK_SUBMISSIONS for t in routes)
    return ClientOdk.from_env() if needs_odk else None


def _build_client_121(routes: Iterable[RouteConfig], *, dry_run: bool) -> Client121 | None:
    needs_121 = any(t.output_mode is OutputMode.PLATFORM_121 for t in routes)
    return Client121.from_env() if needs_121 and not dry_run else None

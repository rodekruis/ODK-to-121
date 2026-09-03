"""CLI entry point."""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv

from odk_to_121.infra.config_reader import ConfigError
from odk_to_121.infra.data_types.config_types import RunTarget
from odk_to_121.infra.orchestrator import run_pipeline
from odk_to_121.infra.utils.api_client import Api121Error
from odk_to_121.infra.utils.logging_config import configure_logging
from odk_to_121.infra.utils.odk_client import OdkClientError

EXIT_SUCCESS = 0
EXIT_PIPELINE_ERROR = 1
EXIT_CONFIG_ERROR = 2

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the YAML configuration file.",
)
@click.option(
    "--run-target",
    required=True,
    type=click.Choice([t.value for t in RunTarget], case_sensitive=False),
    help="Which run target to execute.",
)
@click.option(
    "--issued-at",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    help="Override the pipeline run timestamp (for backfills).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Extract, transform and validate, but send nothing.",
)
@click.option("--verbose", is_flag=True, help="Log at DEBUG level.")
def cli(
    config: Path,
    run_target: str,
    issued_at: datetime | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Pull ODK submissions and push them to 121 as registrations."""
    load_dotenv()
    run_id = uuid.uuid4().hex[:8]
    configure_logging(run_id, level=logging.DEBUG if verbose else logging.INFO)

    try:
        errors = run_pipeline(
            config,
            RunTarget(run_target.lower()),
            issued_at=issued_at,
            dry_run=dry_run,
        )
    except (ConfigError, OdkClientError, Api121Error) as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(EXIT_CONFIG_ERROR)

    if errors:
        for error in errors:
            logger.error(error)
        logger.error("Pipeline completed with %d error(s)", len(errors))
        sys.exit(EXIT_PIPELINE_ERROR)

    logger.info("Pipeline completed successfully")
    sys.exit(EXIT_SUCCESS)


if __name__ == "__main__":
    cli()

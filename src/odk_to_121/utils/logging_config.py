"""Logging configuration. Call once, at the entry point."""

from __future__ import annotations

import logging
import os

NOISY_LOGGERS = ("urllib3", "requests")

# Only this tree is shipped to Azure; third-party loggers stay on the console.
PACKAGE_LOGGER = "odk_to_121"

CONNECTION_STRING_VAR = "APPLICATIONINSIGHTS_CONNECTION_STRING"


class RunIdFilter(logging.Filter):
    """Attaches the run id to every record, so Azure can group a run without parsing messages."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


def configure_logging(run_id: str, *, level: int = logging.INFO) -> None:
    """Stamp every line with the run id so one run can be traced end to end."""
    logging.basicConfig(
        level=level,
        format=f"%(asctime)s %(levelname)-8s [run_id={run_id}] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _configure_azure_monitor(run_id)


def _configure_azure_monitor(run_id: str) -> None:
    """Ship logs to the Log Analytics workspace behind Application Insights, when configured."""
    connection_string = os.environ.get(CONNECTION_STRING_VAR)
    if not connection_string:
        return

    # Imported here so a run without telemetry does not pay for the Azure SDK import.
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=connection_string, logger_name=PACKAGE_LOGGER)

    package_logger = logging.getLogger(PACKAGE_LOGGER)
    # A logger-level filter would skip records from child loggers, a handler-level one does not.
    for handler in package_logger.handlers:
        handler.addFilter(RunIdFilter(run_id))

    package_logger.info("Shipping logs to Azure Monitor")

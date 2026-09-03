"""Logging configuration. Call once, at the entry point."""

from __future__ import annotations

import logging

NOISY_LOGGERS = ("urllib3", "requests")


def configure_logging(run_id: str, *, level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format=f"%(asctime)s %(levelname)-8s [run_id={run_id}] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

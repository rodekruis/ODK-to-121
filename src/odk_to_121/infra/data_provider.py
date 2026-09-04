"""Read-only abstraction over all data sources."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from odk_to_121.infra.data_types.config_types import DataSource, RunTargetConfig
from odk_to_121.infra.data_types.domain_types import OdkSubmissionSet
from odk_to_121.infra.utils.client_odk import ClientOdk
from odk_to_121.infra.utils.data_fetchers import load_submissions

logger = logging.getLogger(__name__)


@dataclass
class LoadedDataSource:
    data_source: DataSource
    data: object | None = None
    error: str | None = None
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)


class DataProvider:
    """Loads configured sources once, then serves them with runtime type checking."""

    def __init__(self, client_odk: ClientOdk | None = None):
        self.client_odk = client_odk
        self.loaded_data: dict[DataSource, LoadedDataSource] = {}

    def load_data(self, run_target: RunTargetConfig) -> list[str]:
        """Load every source for a run target. Returns error messages (empty = success)."""
        container = LoadedDataSource(data_source=run_target.data_source)
        try:
            submissions = load_submissions(run_target, self.client_odk)
        except Exception as exc:  # noqa: BLE001 - one job: report, never crash the run
            container.error = str(exc)
            self.loaded_data[run_target.data_source] = container
            return [f"{run_target.run_target_id}: failed to load {run_target.data_source}: {exc}"]

        container.data = submissions
        container.metadata = {"count": len(submissions), "form_id": submissions.form_id}
        self.loaded_data[run_target.data_source] = container
        logger.info("%s: loaded %d submissions", run_target.run_target_id, len(submissions))
        return []

    def get_data[T](self, source: DataSource, expected_type: type[T]) -> T:
        """Get loaded data with runtime type checking."""
        if source not in self.loaded_data:
            raise KeyError(f"Data source '{source}' not loaded")
        container = self.loaded_data[source]
        if not isinstance(container.data, expected_type):
            raise TypeError(
                f"'{source}' expected {expected_type.__name__}, got {type(container.data).__name__}"
            )
        return container.data

    def get_submissions(self) -> OdkSubmissionSet:
        """Submission set for this run, regardless of which source produced it."""
        for source in self.loaded_data:
            return self.get_data(source, OdkSubmissionSet)
        raise KeyError("No data sources loaded")

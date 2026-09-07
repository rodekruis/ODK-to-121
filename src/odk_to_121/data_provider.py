"""Read-only abstraction over all data sources."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from odk_to_121.data_types.config_types import DataSource, RouteConfig
from odk_to_121.data_types.domain_types import OdkSubmissionSet
from odk_to_121.utils.client_odk import ClientOdk
from odk_to_121.utils.extract import extract_submissions

logger = logging.getLogger(__name__)


@dataclass
class LoadedDataSource:
    """One extracted source plus the outcome of extracting it."""

    data_source: DataSource
    data: object | None = None


class DataProvider:
    """Loads configured sources once, then serves them with runtime type checking."""

    def __init__(self, client_odk: ClientOdk | None = None):
        """Without an ODK client only dummy sources can be extracted."""
        self.client_odk = client_odk
        self.loaded_data: dict[DataSource, LoadedDataSource] = {}

    def extract_data(self, route: RouteConfig) -> list[str]:
        """Extract every source for a route. Returns error messages (empty = success)."""
        container = LoadedDataSource(data_source=route.data_source)
        try:
            submissions = extract_submissions(route, self.client_odk)
        except Exception as exc:  # noqa: BLE001 - one job: report, never crash the run
            self.loaded_data[route.data_source] = container
            return [f"{route.route_id}: failed to load {route.data_source}: {exc}"]

        container.data = submissions
        self.loaded_data[route.data_source] = container
        logger.info("%s: extracted %d submissions", route.route_id, len(submissions))
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

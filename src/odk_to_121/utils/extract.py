"""One extract function per data source, dispatched by `DataSource`."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from odk_to_121.data_types.config_types import DataSource, RouteConfig
from odk_to_121.data_types.domain_types import (
    OdkFormField,
    OdkFormSchema,
    OdkSubmission,
    OdkSubmissionSet,
)
from odk_to_121.utils.client_odk import ClientOdk
from odk_to_121.utils.dummy_data import DUMMY_FORM_FIELDS, DUMMY_SUBMISSION_ROWS

logger = logging.getLogger(__name__)


def extract_form_schema(route: RouteConfig, client_odk: ClientOdk | None) -> OdkFormSchema:
    """Extract the field schema for a route's form from its configured source."""
    match route.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if client_odk is None:
                raise ValueError(f"{route.route_id}: ODK client required for the form schema")
            rows = client_odk.get_form_fields(route.odk.project_id, route.odk.form_id)
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_FORM_FIELDS

    return OdkFormSchema(
        project_id=route.odk.project_id,
        form_id=route.odk.form_id,
        fields=_parsed(route.route_id, rows, OdkFormField.from_api, "form field"),
    )


def extract_submissions(route: RouteConfig, client_odk: ClientOdk | None) -> OdkSubmissionSet:
    """Extract submissions for a route from its configured source."""
    match route.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if client_odk is None:
                raise ValueError(f"{route.route_id}: ODK client required for live submissions")
            rows = client_odk.get_submissions(route.odk.project_id, route.odk.form_id)
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_SUBMISSION_ROWS

    return OdkSubmissionSet(
        project_id=route.odk.project_id,
        form_id=route.odk.form_id,
        submissions=_parsed(route.route_id, rows, OdkSubmission.from_odata, "submission"),
    )


def _parsed[T](
    route_id: str,
    rows: list[dict[str, Any]],
    parse: Callable[[dict[str, Any]], T],
    what: str,
) -> tuple[T, ...]:
    """Parse rows one by one, so a single malformed one cannot lose the whole form."""
    parsed = []
    for row in rows:
        try:
            parsed.append(parse(row))
        except ValueError as exc:
            logger.warning("%s: skipping unparsable %s: %s", route_id, what, exc)
    return tuple(parsed)

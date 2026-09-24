"""One extract function per data source, dispatched by `DataSource`."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from odk_to_121.data_types.config_types import DataSource, RouteConfig
from odk_to_121.data_types.domain_types import (
    OdkFormDefinition,
    OdkFormField,
    OdkFormSchema,
    OdkSubmission,
    OdkSubmissionSet,
)
from odk_to_121.utils.client_odk import ClientOdk
from odk_to_121.utils.dummy_data import (
    DUMMY_FORM_DEFINITION,
    DUMMY_FORM_FIELDS,
    DUMMY_SUBMISSION_ROWS,
)
from odk_to_121.utils.xform import parse_form_definition

logger = logging.getLogger(__name__)


def extract_form_schema(route: RouteConfig, client_odk: ClientOdk | None) -> OdkFormSchema:
    """Extract the field schema for a route's form from its configured source."""
    match route.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if client_odk is None:
                raise ValueError(f"{route.route_id}: ODK client required for the form schema")
            rows = client_odk.get_form_fields(route.odk.project_id, route.odk.form_id)
            xml = client_odk.get_form_definition(route.odk.project_id, route.odk.form_id)
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_FORM_FIELDS
            xml = DUMMY_FORM_DEFINITION

    return OdkFormSchema(
        project_id=route.odk.project_id,
        form_id=route.odk.form_id,
        fields=_parsed(route.route_id, rows, OdkFormField.from_api, "form field"),
        definition=_definition(route.route_id, xml),
    )


def _definition(route_id: str, xml: bytes) -> OdkFormDefinition:
    """Parse the form definition, which decides attribute types.

    A failure here aborts the route on purpose: 121 attributes are created once and never
    retyped, so silently falling back to plain text would strand every select question as
    free text for good. Per-question gaps degrade quietly inside the parser instead.
    """
    definition = parse_form_definition(xml)
    logger.info(
        "%s: read %d questions from the ODK form definition", route_id, len(definition.questions)
    )
    return definition


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

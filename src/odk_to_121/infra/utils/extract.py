"""One extract function per data source, dispatched by `DataSource`."""

from __future__ import annotations

import logging

from odk_to_121.infra.data_types.config_types import DataSource, RouteConfig
from odk_to_121.infra.data_types.domain_types import (
    OdkFormField,
    OdkFormSchema,
    OdkSubmission,
    OdkSubmissionSet,
)
from odk_to_121.infra.utils.client_odk import ClientOdk
from odk_to_121.infra.utils.dummy_data import DUMMY_FORM_FIELDS, DUMMY_SUBMISSION_ROWS

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
        case _:
            raise ValueError(f"{route.route_id}: unknown data source {route.data_source}")

    fields = []
    for row in rows:
        try:
            fields.append(OdkFormField.from_api(row))
        except ValueError as exc:
            logger.warning("%s: skipping unparsable form field: %s", route.route_id, exc)

    return OdkFormSchema(
        project_id=route.odk.project_id,
        form_id=route.odk.form_id,
        fields=tuple(fields),
    )


def extract_submissions(route: RouteConfig, client_odk: ClientOdk | None) -> OdkSubmissionSet:
    """Extract submissions for a route from its configured source."""
    match route.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if client_odk is None:
                raise ValueError(f"{route.route_id}: ODK client required for live submissions")
            rows = client_odk.get_submissions(
                route.odk.project_id,
                route.odk.form_id,
            )
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_SUBMISSION_ROWS
        case _:
            raise ValueError(f"{route.route_id}: unknown data source {route.data_source}")

    submissions = []
    for row in rows:
        try:
            submissions.append(OdkSubmission.from_odata(row))
        except ValueError as exc:
            logger.warning("%s: skipping unparsable submission: %s", route.route_id, exc)

    return OdkSubmissionSet(
        project_id=route.odk.project_id,
        form_id=route.odk.form_id,
        submissions=tuple(submissions),
    )

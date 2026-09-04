"""One fetch function per data source, dispatched by `DataSource`."""

from __future__ import annotations

import logging

from odk_to_121.infra.data_types.config_types import DataSource, RunTargetConfig
from odk_to_121.infra.data_types.domain_types import (
    OdkFormField,
    OdkFormSchema,
    OdkSubmission,
    OdkSubmissionSet,
)
from odk_to_121.infra.utils.client_odk import ClientOdk
from odk_to_121.infra.utils.dummy_data import DUMMY_FORM_FIELDS, DUMMY_SUBMISSION_ROWS

logger = logging.getLogger(__name__)


def load_form_schema(run_target: RunTargetConfig, client_odk: ClientOdk | None) -> OdkFormSchema:
    """Fetch the field schema for a run target's form from its configured source."""
    match run_target.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if client_odk is None:
                raise ValueError(
                    f"{run_target.run_target_id}: ODK client required for the form schema"
                )
            rows = client_odk.get_form_fields(run_target.odk.project_id, run_target.odk.form_id)
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_FORM_FIELDS
        case _:
            raise ValueError(
                f"{run_target.run_target_id}: unknown data source {run_target.data_source}"
            )

    fields = []
    for row in rows:
        try:
            fields.append(OdkFormField.from_api(row))
        except ValueError as exc:
            logger.warning("%s: skipping unparsable form field: %s", run_target.run_target_id, exc)

    return OdkFormSchema(
        project_id=run_target.odk.project_id,
        form_id=run_target.odk.form_id,
        fields=tuple(fields),
    )


def load_submissions(run_target: RunTargetConfig, client_odk: ClientOdk | None) -> OdkSubmissionSet:
    """Fetch submissions for a run target from its configured source."""
    match run_target.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if client_odk is None:
                raise ValueError(
                    f"{run_target.run_target_id}: ODK client required for live submissions"
                )
            rows = client_odk.get_submissions(
                run_target.odk.project_id,
                run_target.odk.form_id,
            )
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_SUBMISSION_ROWS
        case _:
            raise ValueError(
                f"{run_target.run_target_id}: unknown data source {run_target.data_source}"
            )

    submissions = []
    for row in rows:
        try:
            submissions.append(OdkSubmission.from_odata(row))
        except ValueError as exc:
            logger.warning("%s: skipping unparsable submission: %s", run_target.run_target_id, exc)

    return OdkSubmissionSet(
        project_id=run_target.odk.project_id,
        form_id=run_target.odk.form_id,
        submissions=tuple(submissions),
    )

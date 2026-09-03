"""One fetch function per data source, dispatched by `DataSource`."""

from __future__ import annotations

import logging

from odk_to_121.infra.data_types.config_types import DataSource, EntityRunConfig
from odk_to_121.infra.data_types.domain_types import OdkSubmission, OdkSubmissionSet
from odk_to_121.infra.utils.dummy_data import DUMMY_SUBMISSION_ROWS
from odk_to_121.infra.utils.odk_client import OdkClient

logger = logging.getLogger(__name__)


def load_submissions(entity: EntityRunConfig, odk_client: OdkClient | None) -> OdkSubmissionSet:
    """Fetch submissions for an entity from its configured source."""
    match entity.data_source:
        case DataSource.ODK_SUBMISSIONS:
            if odk_client is None:
                raise ValueError(f"{entity.entity_id}: ODK client required for live submissions")
            rows = odk_client.get_submissions(
                entity.odk.project_id,
                entity.odk.form_id,
                submission_filter=entity.odk.submission_filter,
            )
        case DataSource.DUMMY_SUBMISSIONS:
            rows = DUMMY_SUBMISSION_ROWS
        case _:
            raise ValueError(f"{entity.entity_id}: unknown data source {entity.data_source}")

    submissions = []
    for row in rows:
        try:
            submissions.append(OdkSubmission.from_odata(row))
        except ValueError as exc:
            logger.warning("%s: skipping unparsable submission: %s", entity.entity_id, exc)

    return OdkSubmissionSet(
        project_id=entity.odk.project_id,
        form_id=entity.odk.form_id,
        submissions=tuple(submissions),
    )

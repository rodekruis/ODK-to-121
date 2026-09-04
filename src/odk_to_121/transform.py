"""Pure transform: ODK submissions -> 121 registrations. No I/O, no config, no env."""

from __future__ import annotations

import logging

from odk_to_121.infra.data_provider import DataProvider
from odk_to_121.infra.data_submitter import DataSubmitter
from odk_to_121.infra.data_types.domain_types import (
    OdkSubmission,
    RegistrationMapping,
    Scalar,
)

logger = logging.getLogger(__name__)


def transform_submissions(
    data_provider: DataProvider,
    data_submitter: DataSubmitter,
    route_id: str,
    mapping: RegistrationMapping,
) -> None:
    """Map every eligible submission onto a registration, keyed by a stable reference id."""
    submission_set = data_provider.get_submissions()
    if not submission_set.submissions:
        logger.warning("%s: no submissions to transform", route_id)
        return

    skipped_reference = 0
    for submission in submission_set.submissions:
        reference_id = submission.get(mapping.reference_id_field)
        if not isinstance(reference_id, str) or not reference_id:
            skipped_reference += 1
            continue

        data_submitter.create_registration(
            reference_id=reference_id,
            attributes=_map_attributes(submission, mapping),
            preferred_language=mapping.preferred_language,
        )

    logger.info(
        "%s: transformed %d submissions into registrations (%d skipped on missing reference id)",
        route_id,
        len(data_submitter.registrations),
        skipped_reference,
    )


def _map_attributes(submission: OdkSubmission, mapping: RegistrationMapping) -> dict[str, Scalar]:
    return {
        field_mapping.attribute: submission.get(field_mapping.odk_field)
        for field_mapping in mapping.fields
    }

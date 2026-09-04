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


def build_registrations(
    data_provider: DataProvider,
    data_submitter: DataSubmitter,
    entity_id: str,
    mapping: RegistrationMapping,
) -> None:
    """Map every eligible submission onto a registration, keyed by a stable reference id."""
    submission_set = data_provider.get_submissions()
    if not submission_set.submissions:
        logger.warning("%s: no submissions to transform", entity_id)
        return

    skipped_review = 0
    skipped_reference = 0
    for submission in submission_set.submissions:
        if submission.review_state in mapping.skip_review_states:
            skipped_review += 1
            continue

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
        "%s: built %d registrations (%d skipped on review state, %d on missing reference id)",
        entity_id,
        len(data_submitter.registrations),
        skipped_review,
        skipped_reference,
    )


def _map_attributes(submission: OdkSubmission, mapping: RegistrationMapping) -> dict[str, Scalar]:
    attributes: dict[str, Scalar] = {}
    for field_mapping in mapping.fields:
        value = submission.get(field_mapping.odk_field)
        attributes[field_mapping.attribute] = (
            field_mapping.default if value in (None, "") else value
        )
    return attributes

"""Pure transform: ODK submissions -> 121 registrations. No I/O, no config, no env."""

from __future__ import annotations

import logging

from odk_to_121.data_provider import DataProvider
from odk_to_121.data_submitter import DataSubmitter
from odk_to_121.data_types.domain_types import (
    OdkSubmission,
    RegistrationMapping,
    Scalar,
)

logger = logging.getLogger(__name__)

# 121 generic property, not a registration attribute: an ODK question of this name sets
# the language per person. Without it 121 silently falls back to English.
PREFERRED_LANGUAGE_ATTRIBUTE = "preferredLanguage"


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

    for submission in submission_set.submissions:
        attributes = _map_attributes(submission, mapping)
        data_submitter.create_registration(
            reference_id=submission.instance_id,
            attributes=attributes,
            preferred_language=_as_language(attributes.pop(PREFERRED_LANGUAGE_ATTRIBUTE, None)),
        )

    logger.info(
        "%s: transformed %d submissions into registrations",
        route_id,
        len(data_submitter.registrations),
    )


def _map_attributes(submission: OdkSubmission, mapping: RegistrationMapping) -> dict[str, Scalar]:
    """Map ODK submission fields to 121 registration attributes."""
    return {
        field_mapping.attribute: submission.get(field_mapping.odk_field)
        for field_mapping in mapping.fields
    }


def _as_language(value: Scalar) -> str | None:
    """Return the language if set, otherwise None."""
    return value.strip() if isinstance(value, str) and value.strip() else None

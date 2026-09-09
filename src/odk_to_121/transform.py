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
from odk_to_121.data_types.output_types import (
    FSP_CONFIGURATION_ATTRIBUTE,
    PREFERRED_LANGUAGE_ATTRIBUTE,
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

    for submission in submission_set.submissions:
        attributes = _map_attributes(submission, mapping)
        data_submitter.create_registration(
            reference_id=submission.instance_id,
            attributes=attributes,
            preferred_language=_as_text(attributes.pop(PREFERRED_LANGUAGE_ATTRIBUTE, None)),
            fsp_configuration_name=_as_text(attributes.pop(FSP_CONFIGURATION_ATTRIBUTE, None)),
        )

    logger.info(
        "%s: transformed %d submissions into registrations",
        route_id,
        len(data_submitter.registrations),
    )


def _map_attributes(submission: OdkSubmission, mapping: RegistrationMapping) -> dict[str, Scalar]:
    """Map ODK submission fields to 121 registration attributes."""
    attributes: dict[str, Scalar] = {}
    for field_mapping in mapping.fields:
        value = submission.get(field_mapping.odk_field)
        # A plain attribute may stay empty, but 121 validates its built-in columns, so an
        # unanswered one is left out and 121 keeps whatever it already holds.
        if field_mapping.is_built_in and _is_unanswered(value):
            continue
        attributes[field_mapping.attribute] = value
    return attributes


def _is_unanswered(value: Scalar) -> bool:
    """ODK reports a skipped question as a missing key or an empty string."""
    return value is None or (isinstance(value, str) and not value.strip())


def _as_text(value: Scalar) -> str | None:
    """Narrow an answer to the text 121 expects for these columns."""
    return value.strip() if isinstance(value, str) and value.strip() else None

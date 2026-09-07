"""Output validation, run before anything is sent to 121.

These checks mirror what the 121 API rejects, so failures surface locally with
context instead of as a 4xx from the platform.
"""

from __future__ import annotations

from collections import Counter

from odk_to_121.data_types.output_types import RegistrationBatch

MAX_REFERENCE_ID_LENGTH = 200


def check_reference_ids(route_id: str, batch: RegistrationBatch) -> list[str]:
    """Every registration needs a unique referenceId: it is what makes a re-run idempotent."""
    errors = []
    for registration in batch.registrations:
        if not registration.reference_id:
            errors.append(f"{route_id}: registration without referenceId")
        elif len(registration.reference_id) > MAX_REFERENCE_ID_LENGTH:
            errors.append(
                f"{route_id}: referenceId longer than {MAX_REFERENCE_ID_LENGTH} characters "
                f"({len(registration.reference_id)})"
            )

    duplicates = [
        reference_id
        for reference_id, count in Counter(r.reference_id for r in batch.registrations).items()
        if count > 1
    ]
    errors.extend(
        f"{route_id}: duplicate referenceId {reference_id}" for reference_id in duplicates
    )
    return errors


def check_attribute_types(route_id: str, batch: RegistrationBatch) -> list[str]:
    """121 stores each value in one varchar column; a non-scalar 400s the whole batch."""
    errors = []
    for registration in batch.registrations:
        for attribute, value in registration.attributes.items():
            if value is not None and not isinstance(value, str | int | float | bool):
                errors.append(
                    f"{route_id}: registration {registration.reference_id} attribute "
                    f"'{attribute}' has unsupported type {type(value).__name__}"
                )
    return errors


def check_program_id(route_id: str, batch: RegistrationBatch) -> list[str]:
    """Guards against a misconfigured route silently posting into the wrong URL."""
    if batch.program_id <= 0:
        return [f"{route_id}: invalid programId {batch.program_id}"]
    return []


def check_batch(route_id: str, batch: RegistrationBatch) -> list[str]:
    """Run every integrity check and collect all errors."""
    return [
        *check_program_id(route_id, batch),
        *check_reference_ids(route_id, batch),
        *check_attribute_types(route_id, batch),
    ]

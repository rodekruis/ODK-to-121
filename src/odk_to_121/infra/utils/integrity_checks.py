"""Output validation, run before anything is sent to 121.

These checks mirror what the 121 API rejects, so failures surface locally with
context instead of as a 4xx from the platform.
"""

from __future__ import annotations

from collections import Counter

from odk_to_121.infra.data_types.domain_types import FieldMapping
from odk_to_121.infra.data_types.output_types import Registration, RegistrationBatch

MAX_REFERENCE_ID_LENGTH = 200


def check_reference_ids(route_id: str, batch: RegistrationBatch) -> list[str]:
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


def check_required_attributes(
    route_id: str, batch: RegistrationBatch, mappings: tuple[FieldMapping, ...]
) -> list[str]:
    required = [mapping.attribute for mapping in mappings if mapping.required]
    errors = []
    for registration in batch.registrations:
        missing = [
            attribute
            for attribute in required
            if registration.attributes.get(attribute) in (None, "")
        ]
        if missing:
            errors.append(
                f"{route_id}: registration {registration.reference_id} misses "
                f"required attributes {sorted(missing)}"
            )
    return errors


def check_attribute_types(route_id: str, batch: RegistrationBatch) -> list[str]:
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
    if batch.program_id <= 0:
        return [f"{route_id}: invalid programId {batch.program_id}"]
    return []


def check_batch(
    route_id: str, batch: RegistrationBatch, mappings: tuple[FieldMapping, ...]
) -> list[str]:
    """Run every integrity check and collect all errors."""
    return [
        *check_program_id(route_id, batch),
        *check_reference_ids(route_id, batch),
        *check_required_attributes(route_id, batch, mappings),
        *check_attribute_types(route_id, batch),
    ]


def registration_summary(registration: Registration) -> str:
    """Identify a registration in logs without exposing personal data."""
    return f"registration {registration.reference_id}"

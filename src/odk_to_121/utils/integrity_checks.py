"""Output validation, run before anything is sent to 121.

These checks mirror what the 121 API rejects, so failures surface locally with context
instead of as a 4xx from the platform. They quarantine one registration at a time: a
single bad submission must never keep the rest of a run out of 121.
"""

from __future__ import annotations

from collections import Counter

from odk_to_121.data_types.output_types import Registration

MAX_REFERENCE_ID_LENGTH = 200


def check_registrations(
    route_id: str,
    registrations: list[Registration],
    known_fsp_configuration_names: frozenset[str] = frozenset(),
) -> tuple[list[Registration], list[str]]:
    """Split registrations into those safe to load and the errors for the rejected ones."""
    duplicates = _duplicate_reference_ids(registrations)

    loadable: list[Registration] = []
    errors: list[str] = []
    for position, registration in enumerate(registrations, start=1):
        problems = [
            *_check_reference_id(registration, duplicates),
            *_check_attribute_types(registration),
            *_check_fsp_configuration(registration, known_fsp_configuration_names),
        ]
        if problems:
            subject = _describe(registration, position)
            errors.extend(f"{route_id}: {subject} {problem}" for problem in problems)
        else:
            loadable.append(registration)

    return loadable, errors


def _describe(registration: Registration, position: int) -> str:
    """Name the registration an error is about, falling back to its place in the run."""
    if registration.reference_id:
        return f"registration {registration.reference_id}"
    return f"registration #{position}"


def _duplicate_reference_ids(registrations: list[Registration]) -> frozenset[str]:
    """Reference ids claimed more than once; every claimant is rejected, not just the later ones."""
    counts = Counter(r.reference_id for r in registrations if r.reference_id)
    return frozenset(reference_id for reference_id, count in counts.items() if count > 1)


def _check_reference_id(registration: Registration, duplicates: frozenset[str]) -> list[str]:
    """Every registration needs a unique referenceId: it is what makes a re-run idempotent."""
    if not registration.reference_id:
        return ["has no referenceId"]
    if registration.reference_id in duplicates:
        # Nothing says which claimant is the real one, so none of them is loaded.
        return ["shares its referenceId with another registration"]
    if len(registration.reference_id) > MAX_REFERENCE_ID_LENGTH:
        return [
            f"has a referenceId longer than {MAX_REFERENCE_ID_LENGTH} characters "
            f"({len(registration.reference_id)})"
        ]
    return []


def _check_attribute_types(registration: Registration) -> list[str]:
    """121 stores each value in one varchar column; a non-scalar is rejected."""
    return [
        f"attribute '{attribute}' has unsupported type {type(value).__name__}"
        for attribute, value in registration.attributes.items()
        if value is not None and not isinstance(value, str | int | float | bool)
    ]


def _check_fsp_configuration(registration: Registration, known_names: frozenset[str]) -> list[str]:
    """121 rejects a registration naming no FSP configuration, or one it does not have."""
    # Empty means 121 was never contacted (local output, dry run), so there is nothing to check.
    if not known_names:
        return []

    name = registration.fsp_configuration_name
    if name is None:
        return ["names no FSP configuration"]
    if name not in known_names:
        return [
            f"names FSP configuration '{name}', which the 121 program does not have "
            f"({', '.join(sorted(known_names))})"
        ]
    return []

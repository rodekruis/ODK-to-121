from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from odk_to_121.data_types.output_types import Registration, RegistrationBatch
from odk_to_121.utils.integrity_checks import check_batch


def _batch(*registrations: Registration, program_id: int = 1) -> RegistrationBatch:
    """Wrap registrations in a batch so they can be run through the checks."""
    return RegistrationBatch(
        program_id=program_id,
        issued_at=datetime(2026, 1, 15, tzinfo=UTC),
        source_form_id="registration_form",
        registrations=list(registrations),
    )


def _registration(reference_id: str = "uuid:1", **attributes: Any) -> Registration:
    """A valid registration whose attributes individual tests override to break it."""
    defaults: dict[str, Any] = {"fullName": "Ada", "phoneNumber": "3160"}
    return Registration(reference_id=reference_id, attributes={**defaults, **attributes})


def test_valid_batch_has_no_errors() -> None:
    assert check_batch("form-a", _batch(_registration())) == []


def test_detects_duplicate_reference_ids() -> None:
    errors = check_batch("form-a", _batch(_registration(), _registration()))

    assert any("duplicate referenceId" in error for error in errors)


def test_detects_unsupported_attribute_type() -> None:
    errors = check_batch("form-a", _batch(_registration(fullName={"nested": "dict"})))

    assert any("unsupported type dict" in error for error in errors)


def test_detects_invalid_program_id() -> None:
    errors = check_batch("form-a", _batch(_registration(), program_id=0))

    assert any("invalid programId" in error for error in errors)


def test_errors_are_prefixed_with_the_route() -> None:
    errors = check_batch("form-a", _batch(Registration(reference_id="")))

    assert errors and all(error.startswith("form-a: ") for error in errors)

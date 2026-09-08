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


def test_fsp_configurations_are_not_checked_when_121_was_not_contacted() -> None:
    assert check_batch("form-a", _batch(_registration()), frozenset()) == []


def test_detects_a_registration_without_an_fsp_configuration() -> None:
    errors = check_batch("form-a", _batch(_registration()), frozenset({"Excel"}))

    assert any("names no FSP configuration" in error for error in errors)


def test_detects_an_fsp_configuration_the_program_does_not_have() -> None:
    """An ODK question can name anything; 121 would reject the whole batch for one typo."""
    registration = Registration(reference_id="uuid:1", fsp_configuration_name="Exel")

    errors = check_batch("form-a", _batch(registration), frozenset({"Excel"}))

    assert any("'Exel'" in error and "does not" in error for error in errors)

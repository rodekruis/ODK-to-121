from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from odk_to_121.infra.data_types.domain_types import FieldMapping
from odk_to_121.infra.data_types.output_types import Registration, RegistrationBatch
from odk_to_121.infra.utils.integrity_checks import check_batch


def _batch(*registrations: Registration, program_id: int = 1) -> RegistrationBatch:
    return RegistrationBatch(
        program_id=program_id,
        issued_at=datetime(2026, 1, 15, tzinfo=UTC),
        source_form_id="registration_form",
        registrations=list(registrations),
    )


def _registration(reference_id: str = "uuid:1", **attributes: Any) -> Registration:
    defaults: dict[str, Any] = {"fullName": "Ada", "phoneNumber": "3160"}
    return Registration(reference_id=reference_id, attributes={**defaults, **attributes})


def test_valid_batch_has_no_errors(field_mappings: tuple[FieldMapping, ...]) -> None:
    assert check_batch("form-a", _batch(_registration()), field_mappings) == []


def test_detects_duplicate_reference_ids(field_mappings: tuple[FieldMapping, ...]) -> None:
    errors = check_batch("form-a", _batch(_registration(), _registration()), field_mappings)

    assert any("duplicate referenceId" in error for error in errors)


def test_detects_missing_required_attribute(field_mappings: tuple[FieldMapping, ...]) -> None:
    errors = check_batch("form-a", _batch(_registration(phoneNumber="")), field_mappings)

    assert any("required attributes ['phoneNumber']" in error for error in errors)


def test_detects_unsupported_attribute_type(field_mappings: tuple[FieldMapping, ...]) -> None:
    errors = check_batch(
        "form-a", _batch(_registration(fullName={"nested": "dict"})), field_mappings
    )

    assert any("unsupported type dict" in error for error in errors)


def test_detects_invalid_program_id(field_mappings: tuple[FieldMapping, ...]) -> None:
    errors = check_batch("form-a", _batch(_registration(), program_id=0), field_mappings)

    assert any("invalid programId" in error for error in errors)


def test_errors_are_prefixed_with_the_entity() -> None:
    errors = check_batch("form-a", _batch(Registration(reference_id="")), ())

    assert errors and all(error.startswith("form-a: ") for error in errors)

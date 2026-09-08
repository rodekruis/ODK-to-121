from __future__ import annotations

from typing import Any

from odk_to_121.data_types.output_types import Registration
from odk_to_121.utils.integrity_checks import check_registrations


def _registration(reference_id: str = "uuid:1", **attributes: Any) -> Registration:
    """A valid registration whose attributes individual tests override to break it."""
    defaults: dict[str, Any] = {"fullName": "Ada", "phoneNumber": "3160"}
    return Registration(reference_id=reference_id, attributes={**defaults, **attributes})


def test_valid_registrations_are_all_loadable() -> None:
    registrations = [_registration("uuid:1"), _registration("uuid:2")]

    loadable, errors = check_registrations("form-a", registrations)

    assert loadable == registrations
    assert errors == []


def test_a_bad_registration_does_not_hold_back_the_others() -> None:
    good = _registration("uuid:1")
    bad = _registration("uuid:2", fullName={"nested": "dict"})

    loadable, errors = check_registrations("form-a", [good, bad])

    assert loadable == [good]
    assert len(errors) == 1
    assert "unsupported type dict" in errors[0]


def test_both_claimants_of_a_duplicate_reference_id_are_quarantined() -> None:
    """Nothing says which copy is the real one, so neither is loaded."""
    registrations = [_registration("uuid:1"), _registration("uuid:1"), _registration("uuid:2")]

    loadable, errors = check_registrations("form-a", registrations)

    assert [r.reference_id for r in loadable] == ["uuid:2"]
    assert len(errors) == 2
    assert all("shares its referenceId" in error for error in errors)


def test_detects_a_registration_without_a_reference_id() -> None:
    loadable, errors = check_registrations("form-a", [Registration(reference_id="")])

    assert loadable == []
    # With no referenceId to name it, the error falls back to its place in the run.
    assert errors == ["form-a: registration #1 has no referenceId"]


def test_errors_are_prefixed_with_the_route() -> None:
    _, errors = check_registrations("form-a", [Registration(reference_id="")])

    assert errors and all(error.startswith("form-a: ") for error in errors)


def test_fsp_configurations_are_not_checked_when_121_was_not_contacted() -> None:
    registrations = [_registration()]

    loadable, errors = check_registrations("form-a", registrations, frozenset())

    assert loadable == registrations
    assert errors == []


def test_detects_a_registration_without_an_fsp_configuration() -> None:
    loadable, errors = check_registrations("form-a", [_registration()], frozenset({"Excel"}))

    assert loadable == []
    assert any("names no FSP configuration" in error for error in errors)


def test_detects_an_fsp_configuration_the_program_does_not_have() -> None:
    """An ODK question can name anything; a typo would otherwise be rejected by 121."""
    registration = Registration(reference_id="uuid:1", fsp_configuration_name="Exel")

    loadable, errors = check_registrations("form-a", [registration], frozenset({"Excel"}))

    assert loadable == []
    assert any("'Exel'" in error and "does not have" in error for error in errors)

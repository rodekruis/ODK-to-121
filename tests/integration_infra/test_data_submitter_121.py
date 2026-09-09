from __future__ import annotations

import json
import logging

import pytest
import responses

from odk_to_121.data_submitter import DataSubmitter
from odk_to_121.data_types.config_types import OutputMode
from odk_to_121.utils.client_121 import Client121

BASE_URL = "https://121.test"
CREATE_URL = f"{BASE_URL}/api/programs/1/registrations"


def _submitter() -> DataSubmitter:
    """A submitter holding two registrations, ready to load against a mocked 121."""
    submitter = DataSubmitter(
        route_id="form-a",
        program_id=1,
        source_form_id="registration_form",
        default_fsp_configuration_name="Excel",
        known_fsp_configuration_names=frozenset({"Excel"}),
        # Nothing to be polite to here, and the suite must not sleep between registrations.
        client_121=Client121(BASE_URL, "user", "secret", seconds_between_registrations=0),
    )
    submitter.create_registration("uuid:1", {"fullName": "Ada", "phoneNumber": "3160"})
    submitter.create_registration("uuid:2", {"fullName": "Grace", "phoneNumber": "3161"})
    return submitter


def _stub_login_and_existing(*reference_ids: str) -> None:
    """Stub the login and the reference ids 121 already holds."""
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        CREATE_URL,
        json={"data": [{"referenceId": reference_id} for reference_id in reference_ids]},
        status=200,
    )


@pytest.mark.integration
@responses.activate
def test_creates_only_registrations_121_does_not_have() -> None:
    _stub_login_and_existing("uuid:2")
    create = responses.post(CREATE_URL, json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert errors == []
    assert create.call_count == 1
    body = create.calls[0].request.body
    assert isinstance(body, str | bytes)
    # One registration per request, but 121's endpoint still expects an array.
    assert json.loads(body) == [
        {
            "referenceId": "uuid:1",
            "programFspConfigurationName": "Excel",
            "fullName": "Ada",
            "phoneNumber": "3160",
        }
    ]


@pytest.mark.integration
@responses.activate
def test_existing_registrations_are_never_modified() -> None:
    _stub_login_and_existing("uuid:1", "uuid:2")
    create = responses.post(CREATE_URL, json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert errors == []
    assert create.call_count == 0


@pytest.mark.integration
@responses.activate
def test_one_rejection_does_not_hold_back_the_others() -> None:
    _stub_login_and_existing()
    rejected = responses.post(CREATE_URL, json={"message": "bad"}, status=400)
    accepted = responses.post(CREATE_URL, json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert len(errors) == 1
    assert "uuid:1" in errors[0]
    assert "rejected with 400" in errors[0]
    # The second registration was still sent after the first was rejected.
    assert rejected.call_count == 1
    assert accepted.call_count == 1


@pytest.mark.integration
@responses.activate
def test_121_error_is_reported_not_raised() -> None:
    _stub_login_and_existing()
    responses.post(CREATE_URL, json={"message": "bad"}, status=400)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert len(errors) == 2
    assert all("rejected with 400" in error for error in errors)


@pytest.mark.integration
@responses.activate
def test_a_rejected_answer_is_never_echoed_into_the_error() -> None:
    _stub_login_and_existing()
    responses.post(
        CREATE_URL,
        json={
            "errors": [
                {
                    "index": 0,
                    "column": "phoneNumber",
                    "value": "31600000001",
                    "error": "Value is not valid",
                }
            ]
        },
        status=400,
    )

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert "31600000001" not in errors[0]
    assert "[redacted]" in errors[0]
    assert "phoneNumber" in errors[0]


@pytest.mark.integration
@responses.activate
def test_only_the_registrations_failing_a_check_are_held_back() -> None:
    _stub_login_and_existing()
    create = responses.post(CREATE_URL, json={}, status=201)
    submitter = _submitter()
    submitter.create_registration("uuid:1", {"fullName": "Duplicate of Ada"})

    errors = submitter.load_all(OutputMode.PLATFORM_121, "")

    # Both claimants of uuid:1 are quarantined; uuid:2 is loaded regardless.
    assert len(errors) == 2
    assert all("shares its referenceId" in error for error in errors)
    assert create.call_count == 1


@pytest.mark.integration
@responses.activate
def test_the_success_summary_survives_being_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A structured key shadowing a LogRecord attribute raises, and only once INFO is on."""
    _stub_login_and_existing()
    responses.post(CREATE_URL, json={}, status=201)

    with caplog.at_level(logging.INFO, logger="odk_to_121.data_submitter"):
        errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert errors == []
    assert "created 2 of 2 registrations" in caplog.text

from __future__ import annotations

import json

import pytest
import responses

from odk_to_121.data_submitter import DataSubmitter
from odk_to_121.data_types.config_types import OutputMode
from odk_to_121.utils.client_121 import Client121

BASE_URL = "https://121.test"


def _submitter() -> DataSubmitter:
    """A submitter holding two registrations, ready to load against a mocked 121."""
    submitter = DataSubmitter(
        route_id="form-a",
        program_id=1,
        source_form_id="registration_form",
        default_fsp_configuration_name="Excel",
        known_fsp_configuration_names=frozenset({"Excel"}),
        client_121=Client121(BASE_URL, "user", "secret"),
    )
    submitter.create_registration("uuid:1", {"fullName": "Ada", "phoneNumber": "3160"})
    submitter.create_registration("uuid:2", {"fullName": "Grace", "phoneNumber": "3161"})
    return submitter


@pytest.mark.integration
@responses.activate
def test_creates_only_registrations_121_does_not_have() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/registrations",
        json={"data": [{"referenceId": "uuid:2"}]},
        status=200,
    )
    create = responses.post(f"{BASE_URL}/api/programs/1/registrations", json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert errors == []
    body = create.calls[0].request.body
    assert isinstance(body, str | bytes)
    # 121 rejects a created registration without programFspConfigurationName.
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
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/registrations",
        json={"data": [{"referenceId": "uuid:1"}, {"referenceId": "uuid:2"}]},
        status=200,
    )
    create = responses.post(f"{BASE_URL}/api/programs/1/registrations", json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert errors == []
    assert create.call_count == 0


@pytest.mark.integration
@responses.activate
def test_121_error_is_reported_not_raised() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(f"{BASE_URL}/api/programs/1/registrations", json={"data": []}, status=200)
    responses.post(f"{BASE_URL}/api/programs/1/registrations", json={"message": "bad"}, status=400)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "")

    assert len(errors) == 1
    assert "returned 400" in errors[0]


@pytest.mark.integration
@responses.activate
def test_a_rejected_answer_is_never_echoed_into_the_error() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(f"{BASE_URL}/api/programs/1/registrations", json={"data": []}, status=200)
    responses.post(
        f"{BASE_URL}/api/programs/1/registrations",
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

    assert len(errors) == 1
    assert "31600000001" not in errors[0]
    assert "[redacted]" in errors[0]
    assert "phoneNumber" in errors[0]


@pytest.mark.integration
@responses.activate
def test_nothing_is_sent_when_integrity_checks_fail() -> None:
    submitter = _submitter()
    submitter.create_registration("uuid:1", {"fullName": "Duplicate of Ada"})

    errors = submitter.load_all(OutputMode.PLATFORM_121, "")

    assert len(errors) == 1
    assert "duplicate referenceId" in errors[0]
    assert len(responses.calls) == 0

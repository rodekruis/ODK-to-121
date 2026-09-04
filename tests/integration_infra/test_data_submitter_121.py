from __future__ import annotations

import json

import pytest
import responses

from odk_to_121.infra.data_submitter import DataSubmitter
from odk_to_121.infra.data_types.config_types import OutputMode
from odk_to_121.infra.data_types.domain_types import FieldMapping
from odk_to_121.infra.utils.client_121 import Client121

BASE_URL = "https://121.test"


def _submitter() -> DataSubmitter:
    submitter = DataSubmitter(
        route_id="form-a",
        program_id=1,
        source_form_id="registration_form",
        client_121=Client121(BASE_URL, "user", "secret"),
    )
    submitter.create_registration("uuid:1", {"fullName": "Ada", "phoneNumber": "3160"})
    submitter.create_registration("uuid:2", {"fullName": "Grace", "phoneNumber": "3161"})
    return submitter


@pytest.fixture
def mappings() -> tuple[FieldMapping, ...]:
    return (
        FieldMapping(odk_field="person/full_name", attribute="fullName", required=True),
        FieldMapping(odk_field="person/phone_number", attribute="phoneNumber", required=True),
    )


@pytest.mark.integration
@responses.activate
def test_creates_only_registrations_121_does_not_have(
    mappings: tuple[FieldMapping, ...],
) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/registrations",
        json={"data": [{"referenceId": "uuid:2"}]},
        status=200,
    )
    create = responses.post(f"{BASE_URL}/api/programs/1/registrations", json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "", mappings)

    assert errors == []
    body = create.calls[0].request.body
    assert isinstance(body, str | bytes)
    assert json.loads(body) == [{"referenceId": "uuid:1", "fullName": "Ada", "phoneNumber": "3160"}]


@pytest.mark.integration
@responses.activate
def test_existing_registrations_are_never_modified(mappings: tuple[FieldMapping, ...]) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/registrations",
        json={"data": [{"referenceId": "uuid:1"}, {"referenceId": "uuid:2"}]},
        status=200,
    )
    create = responses.post(f"{BASE_URL}/api/programs/1/registrations", json={}, status=201)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "", mappings)

    assert errors == []
    assert create.call_count == 0


@pytest.mark.integration
@responses.activate
def test_121_error_is_reported_not_raised(mappings: tuple[FieldMapping, ...]) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(f"{BASE_URL}/api/programs/1/registrations", json={"data": []}, status=200)
    responses.post(f"{BASE_URL}/api/programs/1/registrations", json={"message": "bad"}, status=400)

    errors = _submitter().load_all(OutputMode.PLATFORM_121, "", mappings)

    assert len(errors) == 1
    assert "returned 400" in errors[0]


@pytest.mark.integration
@responses.activate
def test_nothing_is_sent_when_integrity_checks_fail(mappings: tuple[FieldMapping, ...]) -> None:
    submitter = _submitter()
    submitter.create_registration("uuid:3", {"fullName": "Missing phone"})

    errors = submitter.load_all(OutputMode.PLATFORM_121, "", mappings)

    assert len(errors) == 1
    assert "required attributes" in errors[0]
    assert len(responses.calls) == 0

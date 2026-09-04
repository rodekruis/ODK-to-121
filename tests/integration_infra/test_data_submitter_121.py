from __future__ import annotations

import json

import pytest
import responses

from odk_to_121.infra.data_submitter import DataSubmitter
from odk_to_121.infra.data_types.config_types import OutputMode, SubmissionMode
from odk_to_121.infra.data_types.domain_types import FieldMapping
from odk_to_121.infra.utils.api_client import Api121Client

BASE_URL = "https://121.test"


def _submitter() -> DataSubmitter:
    submitter = DataSubmitter(
        entity_id="form-a",
        program_id=1,
        source_form_id="registration_form",
        api_client=Api121Client(BASE_URL, "user", "secret"),
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
def test_upsert_creates_new_and_patches_existing(mappings: tuple[FieldMapping, ...]) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/registrations",
        json={"data": [{"referenceId": "uuid:2"}]},
        status=200,
    )
    create = responses.post(f"{BASE_URL}/api/programs/1/registrations", json={}, status=201)
    patch = responses.patch(f"{BASE_URL}/api/programs/1/registrations/uuid:2", json={}, status=200)

    errors = _submitter().send_all(OutputMode.API, "", mappings, SubmissionMode.UPSERT)

    assert errors == []
    body = create.calls[0].request.body
    assert isinstance(body, str | bytes)
    assert json.loads(body) == [{"referenceId": "uuid:1", "fullName": "Ada", "phoneNumber": "3160"}]
    assert patch.call_count == 1


@pytest.mark.integration
@responses.activate
def test_api_error_is_reported_not_raised(mappings: tuple[FieldMapping, ...]) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.post(f"{BASE_URL}/api/programs/1/registrations", json={"message": "bad"}, status=400)

    errors = _submitter().send_all(OutputMode.API, "", mappings, SubmissionMode.CREATE)

    assert len(errors) == 1
    assert "returned 400" in errors[0]


@pytest.mark.integration
@responses.activate
def test_nothing_is_sent_when_integrity_checks_fail(mappings: tuple[FieldMapping, ...]) -> None:
    submitter = _submitter()
    submitter.create_registration("uuid:3", {"fullName": "Missing phone"})

    errors = submitter.send_all(OutputMode.API, "", mappings, SubmissionMode.CREATE)

    assert len(errors) == 1
    assert "required attributes" in errors[0]
    assert len(responses.calls) == 0

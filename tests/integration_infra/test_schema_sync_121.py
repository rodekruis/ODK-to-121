from __future__ import annotations

import json

import pytest
import responses

from odk_to_121.infra.data_types.config_types import (
    DataSource,
    OdkFormConfig,
    OutputMode,
    ProgramConfig,
    RunTargetConfig,
)
from odk_to_121.infra.schema_sync import sync_program_attributes
from odk_to_121.infra.utils.client_121 import Client121

BASE_URL = "https://121.test"


def _run_target() -> RunTargetConfig:
    return RunTargetConfig(
        run_target_id="form-a",
        data_source=DataSource.DUMMY_SUBMISSIONS,
        odk=OdkFormConfig(project_id=1, form_id="registration_form"),
        program=ProgramConfig(program_id=1),
        output_mode=OutputMode.PLATFORM_121,
        output_path="",
        required_attributes=("fullName", "phoneNumber"),
    )


def _client() -> Client121:
    return Client121(BASE_URL, "user", "secret")


@pytest.mark.integration
@responses.activate
def test_creates_only_the_attributes_121_is_missing() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/attributes",
        json={"data": [{"name": "fullName", "type": "text"}]},
        status=200,
    )
    create = responses.post(
        f"{BASE_URL}/api/programs/1/registration-attributes", json={}, status=201
    )

    plan, errors = sync_program_attributes(_run_target(), None, _client())

    assert errors == []
    assert plan is not None
    assert create.call_count == 2
    bodies = []
    for call in create.calls:
        body = call.request.body
        assert isinstance(body, str | bytes)
        bodies.append(json.loads(body))
    assert {body["name"]: body["type"] for body in bodies} == {
        "phoneNumber": "text",
        "householdSize": "numeric",
    }
    assert bodies[0]["isRequired"] is False
    assert bodies[0]["label"] == {"en": "phoneNumber"}


@pytest.mark.integration
@responses.activate
def test_nothing_is_created_when_the_program_is_already_in_sync() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/attributes",
        json={
            "data": [
                {"name": "fullName", "type": "text"},
                {"name": "phoneNumber", "type": "text"},
                {"name": "householdSize", "type": "numeric"},
            ]
        },
        status=200,
    )
    create = responses.post(
        f"{BASE_URL}/api/programs/1/registration-attributes", json={}, status=201
    )

    plan, errors = sync_program_attributes(_run_target(), None, _client())

    assert errors == []
    assert plan is not None
    assert create.call_count == 0


@pytest.mark.integration
@responses.activate
def test_failed_creation_is_reported_and_blocks_the_run() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(f"{BASE_URL}/api/programs/1/attributes", json={"data": []}, status=200)
    responses.post(
        f"{BASE_URL}/api/programs/1/registration-attributes",
        json={"message": "nope"},
        status=400,
    )

    plan, errors = sync_program_attributes(_run_target(), None, _client())

    assert plan is None
    assert len(errors) == 3
    assert "returned 400" in errors[0]


@pytest.mark.integration
def test_local_output_derives_the_plan_without_calling_121() -> None:
    plan, errors = sync_program_attributes(_run_target(), None, None)

    assert errors == []
    assert plan is not None
    assert [a.name for a in plan.attributes] == ["fullName", "phoneNumber", "householdSize"]

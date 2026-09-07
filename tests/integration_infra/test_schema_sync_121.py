from __future__ import annotations

import json
import logging

import pytest
import responses

from odk_to_121.data_types.config_types import (
    DataSource,
    OdkFormConfig,
    OutputMode,
    ProgramConfig,
    RouteConfig,
)
from odk_to_121.schema_sync import sync_program_attributes
from odk_to_121.utils.client_121 import Client121

BASE_URL = "https://121.test"


def _run_route() -> RouteConfig:
    """A route on dummy data that still loads to 121, so schema sync talks to the API."""
    return RouteConfig(
        route_id="form-a",
        data_source=DataSource.DUMMY_SUBMISSIONS,
        odk=OdkFormConfig(project_id=1, form_id="registration_form"),
        program=ProgramConfig(program_id=1),
        output_mode=OutputMode.PLATFORM_121,
        output_path="",
        fsp_configuration_name="Excel",
    )


def _client() -> Client121:
    """A 121 client pointed at the mocked base url."""
    return Client121(BASE_URL, "user", "secret")


def _stub_program(*naming_convention: str) -> None:
    """Stub the program read that schema sync makes for the naming convention."""
    responses.get(
        f"{BASE_URL}/api/programs/1",
        json={"fullnameNamingConvention": list(naming_convention)},
        status=200,
    )


@pytest.mark.integration
@responses.activate
def test_creates_only_the_attributes_121_is_missing() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    _stub_program("fullName")
    responses.get(
        f"{BASE_URL}/api/programs/1/attributes",
        json={"data": [{"name": "fullName", "type": "text"}]},
        status=200,
    )
    create = responses.post(
        f"{BASE_URL}/api/programs/1/registration-attributes", json={}, status=201
    )

    plan, errors = sync_program_attributes(_run_route(), None, _client())

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
def test_existing_attributes_are_requested_with_the_include_flag() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    _stub_program("fullName")
    listing = responses.get(
        f"{BASE_URL}/api/programs/1/attributes",
        json={"data": []},
        status=200,
        match=[
            responses.matchers.query_param_matcher({"includeProgramRegistrationAttributes": "true"})
        ],
    )
    responses.post(f"{BASE_URL}/api/programs/1/registration-attributes", json={}, status=201)

    _, errors = sync_program_attributes(_run_route(), None, _client())

    assert errors == []
    assert listing.call_count == 1


@pytest.mark.integration
@responses.activate
def test_nothing_is_created_when_the_program_is_already_in_sync() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    _stub_program("fullName")
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

    plan, errors = sync_program_attributes(_run_route(), None, _client())

    assert errors == []
    assert plan is not None
    assert create.call_count == 0


@pytest.mark.integration
@responses.activate
def test_an_attribute_121_requires_but_odk_lacks_only_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    _stub_program("fullName")
    responses.get(
        f"{BASE_URL}/api/programs/1/attributes",
        json={
            "data": [
                {"name": "fullName", "type": "text"},
                {"name": "phoneNumber", "type": "text"},
                {"name": "householdSize", "type": "numeric"},
                {"name": "nationalId", "type": "text", "isRequired": True},
            ]
        },
        status=200,
    )

    with caplog.at_level(logging.WARNING):
        plan, errors = sync_program_attributes(_run_route(), None, _client())

    assert errors == []
    assert plan is not None
    assert "121 requires attribute 'nationalId'" in caplog.text


@pytest.mark.integration
@responses.activate
def test_a_naming_convention_field_missing_from_odk_only_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    _stub_program("firstName", "lastName")
    responses.get(
        f"{BASE_URL}/api/programs/1/attributes",
        json={
            "data": [
                {"name": "fullName", "type": "text"},
                {"name": "phoneNumber", "type": "text"},
                {"name": "householdSize", "type": "numeric"},
                {"name": "firstName", "type": "text"},
                {"name": "lastName", "type": "text"},
            ]
        },
        status=200,
    )

    with caplog.at_level(logging.WARNING):
        plan, errors = sync_program_attributes(_run_route(), None, _client())

    assert errors == []
    assert plan is not None
    assert "builds the registration name from attribute 'firstName'" in caplog.text
    assert "builds the registration name from attribute 'lastName'" in caplog.text


@pytest.mark.integration
@responses.activate
def test_an_unreadable_program_does_not_stop_the_sync(caplog: pytest.LogCaptureFixture) -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(f"{BASE_URL}/api/programs/1", json={"message": "nope"}, status=500)
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

    with caplog.at_level(logging.WARNING):
        plan, errors = sync_program_attributes(_run_route(), None, _client())

    assert errors == []
    assert plan is not None
    assert "could not read 121 program" in caplog.text


@pytest.mark.integration
@responses.activate
def test_failed_creation_is_reported_and_blocks_the_run() -> None:
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    _stub_program("fullName")
    responses.get(f"{BASE_URL}/api/programs/1/attributes", json={"data": []}, status=200)
    responses.post(
        f"{BASE_URL}/api/programs/1/registration-attributes",
        json={"message": "nope"},
        status=400,
    )

    plan, errors = sync_program_attributes(_run_route(), None, _client())

    assert plan is None
    assert len(errors) == 3
    assert "returned 400" in errors[0]


@pytest.mark.integration
def test_local_output_derives_the_plan_without_calling_121() -> None:
    plan, errors = sync_program_attributes(_run_route(), None, None)

    assert errors == []
    assert plan is not None
    assert [a.name for a in plan.attributes] == ["fullName", "phoneNumber", "householdSize"]

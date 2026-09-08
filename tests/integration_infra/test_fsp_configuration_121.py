from __future__ import annotations

import pytest
import responses

from odk_to_121.data_types.config_types import (
    DataSource,
    OdkFormConfig,
    OutputMode,
    ProgramConfig,
    RouteConfig,
)
from odk_to_121.data_types.domain_types import FieldMapping
from odk_to_121.fsp_configuration import resolve_fsp_configuration
from odk_to_121.utils.client_121 import Client121

BASE_URL = "https://121.test"

FORM_MAPPINGS = (FieldMapping(odk_field="person/fullName", attribute="fullName"),)
FORM_MAPPINGS_WITH_FSP_QUESTION = (
    *FORM_MAPPINGS,
    FieldMapping(
        odk_field="programFspConfigurationName",
        attribute="programFspConfigurationName",
        is_built_in=True,
    ),
)

pytestmark = pytest.mark.integration


def _route() -> RouteConfig:
    """A route loading into 121 program 1."""
    return RouteConfig(
        route_id="form-a",
        data_source=DataSource.ODK_SUBMISSIONS,
        odk=OdkFormConfig(project_id=1, form_id="registration_form"),
        program=ProgramConfig(program_id=1),
        output_mode=OutputMode.PLATFORM_121,
        output_path="",
    )


def _client() -> Client121:
    """A 121 client pointed at the mocked base url."""
    return Client121(BASE_URL, "user", "secret")


def _stub(*names: str, status: int = 200) -> None:
    """Stub the program's FSP configurations, which 121 returns as a bare array."""
    responses.post(f"{BASE_URL}/api/users/login", json={"access_token": "t"}, status=201)
    responses.get(
        f"{BASE_URL}/api/programs/1/fsp-configurations",
        json=[{"name": name, "fspName": name} for name in names],
        status=status,
    )


@responses.activate
def test_a_single_fsp_configuration_needs_no_form_question_and_no_config() -> None:
    _stub("Excel")

    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS, _client())

    assert errors == []
    assert plan is not None
    assert plan.default_name == "Excel"
    assert plan.known_names == frozenset({"Excel"})


@responses.activate
def test_several_fsp_configurations_without_a_form_question_abort_the_route() -> None:
    _stub("Excel", "Airtel")

    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS, _client())

    assert plan is None
    assert len(errors) == 1
    assert "Airtel" in errors[0] and "Excel" in errors[0]
    assert "programFspConfigurationName" in errors[0]


@responses.activate
def test_several_fsp_configurations_are_fine_when_the_form_picks_one() -> None:
    _stub("Excel", "Airtel")

    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS_WITH_FSP_QUESTION, _client())

    assert errors == []
    assert plan is not None
    # Nothing is stamped on the batch; each registration carries its own answer.
    assert plan.default_name is None
    assert plan.known_names == frozenset({"Excel", "Airtel"})


@responses.activate
def test_a_program_without_fsp_configurations_aborts_the_route() -> None:
    _stub()

    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS, _client())

    assert plan is None
    assert errors == [
        "form-a: 121 program 1 has no FSP configurations, so it cannot accept "
        "registrations; add one in the 121 portal"
    ]


@responses.activate
def test_an_unreadable_fsp_configuration_list_aborts_the_route() -> None:
    _stub(status=403)

    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS, _client())

    assert plan is None
    assert len(errors) == 1
    assert "could not list the FSP configurations" in errors[0]


@responses.activate
def test_an_unreadable_fsp_configuration_list_only_warns_when_the_form_picks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The form still supplies a name, so the run continues without local validation."""
    _stub(status=403)

    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS_WITH_FSP_QUESTION, _client())

    assert errors == []
    assert plan is not None
    assert plan.known_names == frozenset()
    assert "go unchecked" in caplog.text


def test_121_is_not_contacted_without_a_client() -> None:
    """Local output and dry runs have nothing to reconcile with."""
    plan, errors = resolve_fsp_configuration(_route(), FORM_MAPPINGS, None)

    assert errors == []
    assert plan is not None
    assert plan.default_name is None
    assert plan.known_names == frozenset()

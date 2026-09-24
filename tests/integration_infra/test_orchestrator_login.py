from __future__ import annotations

from pathlib import Path

import pytest
import responses

from odk_to_121.data_types.config_types import Environment
from odk_to_121.orchestrator import run_pipeline
from odk_to_121.utils.client_121 import Client121Error
from odk_to_121.utils.client_odk import ClientOdkError

ODK_URL = "https://odk.test"
URL_121 = "https://121.test"

CONFIG = """
environments:
  prod:
    routes:
      - id: form-a
        data_source: odk_submissions
        odk:
          project_id: 1
          form_id: registration_form
        121:
          program_id: 1
        output:
          mode: 121
"""

FORM_DEFINITION = b"""<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml">
  <h:body><input ref="/data/fullName"/></h:body>
</h:html>
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ODK_BASE_URL", ODK_URL)
    monkeypatch.setenv("ODK_USERNAME", "user")
    monkeypatch.setenv("ODK_PASSWORD", "secret")
    monkeypatch.setenv("URL_121", URL_121)
    monkeypatch.setenv("USERNAME_121", "user")
    monkeypatch.setenv("PASSWORD_121", "secret")


@pytest.mark.integration
@responses.activate
def test_rejected_121_credentials_abort_the_run(config_path: Path) -> None:
    """A 401 is a config error, so it must escape run_pipeline rather than become a route error."""
    responses.post(f"{ODK_URL}/v1/sessions", json={"token": "t"}, status=200)
    responses.post(f"{URL_121}/api/users/login", status=401)

    with pytest.raises(Client121Error, match="401"):
        run_pipeline(config_path, Environment.PROD)


@pytest.mark.integration
@responses.activate
def test_rejected_odk_credentials_abort_the_run(config_path: Path) -> None:
    responses.post(f"{ODK_URL}/v1/sessions", status=401)

    with pytest.raises(ClientOdkError, match="401"):
        run_pipeline(config_path, Environment.PROD)


@pytest.mark.integration
@responses.activate
def test_a_dry_run_never_authenticates_against_121(config_path: Path) -> None:
    """No 121 client is built, so a broken 121 must not stop a dry run."""
    responses.post(f"{ODK_URL}/v1/sessions", json={"token": "t"}, status=200)
    responses.get(
        f"{ODK_URL}/v1/projects/1/forms/registration_form/fields",
        json=[{"name": "fullName", "path": "/fullName", "type": "string"}],
        status=200,
    )
    responses.get(
        f"{ODK_URL}/v1/projects/1/forms/registration_form.xml",
        body=FORM_DEFINITION,
        content_type="application/xml",
        status=200,
    )
    responses.get(
        f"{ODK_URL}/v1/projects/1/forms/registration_form.svc/Submissions",
        json={"value": []},
        status=200,
    )

    errors = run_pipeline(config_path, Environment.PROD, dry_run=True)

    assert errors == []
    assert not any(str(call.request.url).startswith(URL_121) for call in responses.calls)

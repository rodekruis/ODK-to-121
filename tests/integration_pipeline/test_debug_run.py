from __future__ import annotations

import json
from pathlib import Path

import pytest

from odk_to_121.infra.data_types.config_types import Environment
from odk_to_121.infra.orchestrator import run_pipeline

CONFIG = """
environments:
  debug:
    routes:
      - id: form-a
        data_source: dummy_submissions
        odk:
          project_id: 1
          form_id: registration_form
        121:
          program_id: 1
          preferred_language: en
        required_attributes: [fullName, phoneNumber]
        output:
          mode: local
          path: {output_path}
"""


@pytest.mark.integration
def test_debug_run_writes_registrations_to_disk(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "output"
    config_path.write_text(
        CONFIG.format(output_path=json.dumps(str(output_path))), encoding="utf-8"
    )

    errors = run_pipeline(config_path, Environment.DEBUG)

    assert errors == []
    written = list(output_path.glob("form-a/*/registrations.json"))
    assert len(written) == 1

    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["programId"] == 1
    assert len(payload["registrations"]) == 3
    assert payload["registrations"][0]["referenceId"].startswith("uuid:")
    assert payload["registrations"][0]["preferredLanguage"] == "en"


@pytest.mark.integration
def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "output"
    config_path.write_text(
        CONFIG.format(output_path=json.dumps(str(output_path))), encoding="utf-8"
    )

    errors = run_pipeline(config_path, Environment.DEBUG, dry_run=True)

    assert errors == []
    assert not output_path.exists()

from __future__ import annotations

from pathlib import Path

import pytest

from odk_to_121.infra.config_reader import ConfigError, ConfigReader
from odk_to_121.infra.data_types.config_types import DataSource, OutputMode, RunTarget

REPO_CONFIG = Path("src/odk_to_121/infra/configs/registrations.yaml")

VALID_CONFIG = """
pipeline_type: registrations
run_targets:
  debug:
    entities:
      - id: form-a
        data_source: dummy_submissions
        odk:
          project_id: 1
          form_id: form_a
        program:
          program_id: 2
        field_mappings:
          - odk_field: person/full_name
            attribute: fullName
            required: true
        output:
          mode: local
          path: output/
"""


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_valid_config(tmp_path: Path) -> None:
    reader = ConfigReader()

    assert reader.load(_write(tmp_path, VALID_CONFIG))

    entity = reader.get_run_config(RunTarget.DEBUG).entities["form-a"]
    assert entity.data_source is DataSource.DUMMY_SUBMISSIONS
    assert entity.output_mode is OutputMode.LOCAL
    assert entity.program.program_id == 2
    assert entity.field_mappings[0].required is True


def test_repo_config_is_valid() -> None:
    reader = ConfigReader()

    assert reader.load(REPO_CONFIG)
    assert set(reader.run_configs) == set(RunTarget)


@pytest.mark.parametrize(
    "replacement",
    [
        ("pipeline_type: registrations", "pipeline_type: unknown"),
        ("data_source: dummy_submissions", "data_source: carrier_pigeon"),
        ("mode: local", "mode: telegram"),
        ("program_id: 2", "program_id: 0"),
        ("  debug:", "  staging:"),
    ],
)
def test_rejects_invalid_config(tmp_path: Path, replacement: tuple[str, str]) -> None:
    content = VALID_CONFIG.replace(*replacement)

    assert ConfigReader().load(_write(tmp_path, content)) is False


def test_rejects_duplicate_attribute_mapping(tmp_path: Path) -> None:
    content = VALID_CONFIG.replace(
        """          - odk_field: person/full_name
            attribute: fullName
            required: true
""",
        """          - odk_field: person/full_name
            attribute: fullName
            required: true
          - odk_field: person/other_name
            attribute: fullName
""",
    )

    assert ConfigReader().load(_write(tmp_path, content)) is False


def test_get_run_config_raises_for_undefined_target(tmp_path: Path) -> None:
    reader = ConfigReader()
    reader.load(_write(tmp_path, VALID_CONFIG))

    with pytest.raises(ConfigError):
        reader.get_run_config(RunTarget.PROD)

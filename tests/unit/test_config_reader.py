from __future__ import annotations

from pathlib import Path

import pytest

from odk_to_121.infra.config_reader import ConfigError, ConfigReader
from odk_to_121.infra.data_types.config_types import DataSource, Environment, OutputMode

REPO_CONFIG = Path("src/odk_to_121/infra/configs/registrations.yaml")

VALID_CONFIG = """
environments:
  debug:
    routes:
      - id: form-a
        data_source: dummy_submissions
        odk:
          project_id: 1
          form_id: form_a
        121:
          program_id: 2
        required_attributes: [fullName]
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

    route = reader.get_run_config(Environment.DEBUG).routes["form-a"]
    assert route.data_source is DataSource.DUMMY_SUBMISSIONS
    assert route.output_mode is OutputMode.LOCAL
    assert route.program.program_id == 2
    assert route.required_attributes == ("fullName",)


def test_repo_config_is_valid() -> None:
    reader = ConfigReader()

    assert reader.load(REPO_CONFIG)
    assert set(reader.run_configs) == set(Environment)


@pytest.mark.parametrize(
    "replacement",
    [
        ("data_source: dummy_submissions", "data_source: carrier_pigeon"),
        ("mode: local", "mode: telegram"),
        ("program_id: 2", "program_id: 0"),
        ("  debug:", "  staging:"),
    ],
)
def test_rejects_invalid_config(tmp_path: Path, replacement: tuple[str, str]) -> None:
    content = VALID_CONFIG.replace(*replacement)

    assert ConfigReader().load(_write(tmp_path, content)) is False


def test_rejects_duplicate_required_attribute(tmp_path: Path) -> None:
    content = VALID_CONFIG.replace(
        "required_attributes: [fullName]", "required_attributes: [fullName, fullName]"
    )

    assert ConfigReader().load(_write(tmp_path, content)) is False


def test_get_run_config_raises_for_undefined_target(tmp_path: Path) -> None:
    reader = ConfigReader()
    reader.load(_write(tmp_path, VALID_CONFIG))

    with pytest.raises(ConfigError):
        reader.get_run_config(Environment.PROD)

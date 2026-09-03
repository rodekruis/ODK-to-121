# ODK-to-121

ETL pipeline that pulls form submissions from **ODK Central** and pushes them to the
**121 platform** as registrations. Built by [NLRC 510](https://www.510.global/).

## How it works

```
ODK Central (OData)  ──extract──▶  OdkSubmission  ──transform──▶  Registration  ──load──▶  121
```

- **Extract** — `infra/utils/odk_client.py` reads the OData `Submissions` feed of one form,
  following pagination, and parses every row into an `OdkSubmission` (nested groups flattened
  to `group/field` keys).
- **Transform** — `registrations/transform.py` is pure: it maps ODK fields onto 121 attributes
  using the YAML-declared `field_mappings`, skips submissions in unwanted review states, and
  derives a deterministic `referenceId` from the ODK instance id.
- **Load** — `infra/data_submitter.py` runs all integrity checks first and aborts on any error,
  then dispatches: `local` writes an atomic JSON file, `api` creates new registrations in one
  batched request and (in `upsert` mode) patches the ones that already exist.

Because the `referenceId` is derived from the ODK instance id, reruns are idempotent.

## Quickstart

```bash
uv sync
cp example.env .env          # fill in ODK and 121 credentials
uv run run-pipeline --config src/odk_to_121/infra/configs/registrations.yaml --run-target debug
```

The `debug` target uses dummy submissions and writes to `output/`, so it needs no credentials.

### CLI

| Option | Purpose |
|--------|---------|
| `--config` | Path to the YAML config |
| `--run-target` | `debug`, `test` or `prod` |
| `--issued-at` | Override the run timestamp (backfills) |
| `--dry-run` | Extract, transform and validate, but send nothing |
| `--verbose` | Log at DEBUG level |

Exit codes: `0` success, `1` pipeline errors, `2` config/credential error.

## Configuration

`src/odk_to_121/infra/configs/registrations.yaml` defines, per run target, which ODK form feeds
which 121 program and how fields map:

```yaml
field_mappings:
  - odk_field: person/full_name   # flattened ODK path
    attribute: fullName           # 121 registration attribute
    required: true                # enforced by the integrity checks
  - odk_field: household/size
    attribute: householdSize
    default: 1                    # used when the answer is empty
```

Secrets live in `.env` only (see `example.env`). Precedence: CLI flags > env vars > YAML > defaults.

## Tests

```bash
uv run pytest tests/unit/          # pure logic, no I/O
uv run pytest -m integration       # infra + end-to-end with mocked APIs
uv run ruff check . && uv run ty check
```

## Open items

- The ODK form id, project id and field mappings in the config are placeholders — replace them
  with the real form.
- `dummy_data.py` exists for the `debug` target; swap it for a real ODK test form when available.
- The 121 PATCH contract (audit `reason`) should be verified against the target instance.

## AI Disclaimer

Parts of the code in this repository were written and reviewed with the assistance of AI tools, including large language models (LLMs).

All AI-generated code has been reviewed by human contributors before being merged. The humans involved take responsibility for the correctness and quality of the code.

If you have questions or concerns, please contact the maintainers.

# ODK-to-121

ETL pipeline that pulls form submissions from **ODK Central** and pushes them to the
**121 platform** as registrations. Built by [NLRC 510](https://www.510.global/).


## Design principle

**ODK is a data collection tool. 121 is where data is managed.** All cleaning, validation,
triage and correction happen in the 121 portal, so this pipeline is deliberately simple:
sends every new ODK submission to 121 and stops. It does not filter submissions and never
updates a 121 registration.

## How it works

```
ODK Central (OData)  ──extract──▶  OdkSubmission  ──transform──▶  Registration  ──load──▶  121
```

- **Schema sync** — before anything is extracted, `infra/schema_sync.py` reads the ODK form's
  field schema, derives the 121 registration attributes it implies, and creates the ones the
  program is missing. 121 rejects attributes a program does not know about, so this has to
  succeed first. It is additive: fields removed from the ODK form are left alone in 121 so the
  data collected against them survives.
- **Extract** — `infra/utils/client_odk.py` reads the OData `Submissions` feed of one form,
  following pagination, and parses every row into an `OdkSubmission` (nested groups flattened
  to `group/field` keys).
- **Transform** — `transform.py` is pure: it maps ODK fields onto 121 attributes
  using the synced schema and derives a deterministic `referenceId` from the ODK instance id.
  Every submission in the form is mapped.
- **Load** — `infra/data_submitter.py` runs all integrity checks first and aborts on any error,
  then dispatches: `local` writes an atomic JSON file, `121` creates the registrations 121 does
  not have yet in one batched request. Existing registrations are left untouched, because 121
  owns the record once it has one.

Because the `referenceId` is derived from the ODK instance id, reruns only ever add what is
missing.

## Schema sync

The mapping rules mirror the 121 platform's own Kobo integration, so an ODK-fed program looks
like a Kobo-fed one.

- **Names.** The ODK question name becomes the 121 attribute name; the group path is dropped,
  so `person/fullName` becomes `fullName`. Two groups cannot share a leaf name — that is a
  hard error rather than a silent overwrite.
- **Types.** `int` and `decimal` become `numeric`; everything else storable becomes `text`.
  Dates and geo values are deliberately `text`, because 121's typed attributes reject the
  formats ODK produces.
- **Not created.** Group nodes, attachments, ODK Collect metadata (`start`, `deviceid`,
  `instanceID`, …) and 121's own built-in columns (`referenceId`, `preferredLanguage`,
  `maxPayments`, …) are skipped. Repeats and names 121 generates itself (`paymentCount`, …)
  abort the run.
- **Never updated.** An existing attribute is left untouched even if the ODK form changed its
  type; the mismatch is logged as a warning.

Because ODK's fields endpoint carries no question labels or choice lists, every select question
becomes a plain `text` attribute holding the raw choice code, and the attribute label falls back
to the field name. Reading labels and choices would mean parsing the XForm definition.

FSP-required attributes (`fullName`, `phoneNumber`, …) are not created for you — name the ODK
questions exactly as 121 expects them.

## Quickstart

```bash
uv sync
cp example.env .env          # fill in ODK and 121 credentials
uv run run-pipeline --config src/odk_to_121/infra/configs/registrations.yaml --environment debug
```

The `debug` target uses dummy submissions and writes to `output/`, so it needs no credentials.

### CLI

| Option | Purpose |
|--------|---------|
| `--config` | Path to the YAML config |
| `--environment` | `debug`, `test` or `prod` |
| `--issued-at` | Override the run timestamp (backfills) |
| `--dry-run` | Extract, transform and validate, but send nothing |
| `--verbose` | Log at DEBUG level |

Exit codes: `0` success, `1` pipeline errors, `2` config/credential error.

## Configuration

`src/odk_to_121/infra/configs/registrations.yaml` defines, per run target, which ODK form feeds
which 121 program. Field mappings are **not** configured — they are derived from the form:

```yaml
odk:
  project_id: 1
  form_id: registration_form
121:
  program_id: 1
  preferred_language: en
required_attributes: [fullName, phoneNumber]   # enforced by the integrity checks
```

Every submission the form holds becomes a registration.

`required_attributes` is deliberately manual: ODK's `required` bind stays true even when skip
logic makes a question irrelevant, so it cannot be mirrored.

Secrets live in `.env` only (see `example.env`). Precedence: CLI flags > env vars > YAML > defaults.

## Tests

```bash
uv run pytest tests/unit/          # pure logic, no I/O
uv run pytest -m integration       # infra + end-to-end with mocked APIs
uv run ruff check . && uv run ty check
```

## Open items

- The ODK form id and project id in the config are placeholders — replace them with the real form.
- `dummy_data.py` provides the form schema and submissions for the `debug` target; swap it for a
  real ODK test form when available.
- The 121 read endpoint for existing attributes (`GET /api/programs/{id}/attributes`) and the
  PATCH contract (audit `reason`) should both be verified against the target instance.
- Select questions land as raw choice codes. If caseworkers need labels, schema sync has to read
  the XForm definition instead of the fields endpoint.

## AI Disclaimer

Parts of the code in this repository were written and reviewed with the assistance of AI tools, including large language models (LLMs).

All AI-generated code has been reviewed by human contributors before being merged. The humans involved take responsibility for the correctness and quality of the code.

If you have questions or concerns, please contact the maintainers.

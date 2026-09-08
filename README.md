# ODK-to-121

ETL pipeline that pulls form submissions from **ODK Central** and pushes them to the
**121 platform** as registrations.


## Design principle

**ODK is a data collection tool, 121 is where data is managed.** Data cleaning, validation,
triage and correction happen in the 121 portal, so this pipeline is deliberately simple: it
loads every new ODK submission into 121 and stops. It **does not filter** ODK submissions and
**never updates** 121 registrations.

## How it works

```
ODK Central (OData)  ──extract──▶  OdkSubmission  ──transform──▶  Registration  ──load──▶  121
```

- **Schema sync**: before anything is extracted, `schema_sync.py` 
  - reads the ODK form's field (i.e. question) schema
  - derives the 121 registration attributes it implies (one field = one attribute)
  - creates in 121 the registration attributes that the program is missing.
  
  It is additive: fields removed from the ODK form are left alone in 121 so the
  data of the corresponding attribute survives. Existing attributes are never updated,
  a change in ODK type only raises a warning.
- **Extract**: `utils/client_odk.py` reads the OData `Submissions` feed of one form, following pagination, and parses every row into an `OdkSubmission` (nested groups flattened to `group/field` keys).
- **Transform**: `transform.py` maps ODK fields onto 121 attributes
  using the synced schema and uses the ODK instance id as the `referenceId`.
  Every submission in the form is mapped.
- **Load**: `data_submitter.py` runs the integrity checks, holds back only the registrations that
  fail them, then produces an output: output mode `local` writes a JSON file, output mode `121`
  creates each registration in its own request, at most one per second. Only missing registrations
  are created. Existing registrations are not updated.

One bad submission never blocks a run. A registration that fails a check, or that 121 rejects, is
reported on its own line and the rest is still loaded. The run then exits non-zero so a scheduler or
alert rule notices, and re-running is safe: everything already in 121 is skipped by `referenceId`,
so only the failures are retried.

## Schema sync

The mapping rules mirror the 121 platform's own
[Kobo integration](https://github.com/global-121/121-platform/tree/main/services/121-service/src/kobo).

- **Names**: the ODK question name becomes the 121 attribute name; the group path is dropped,
  so `person/fullName` becomes `fullName`. Two groups cannot share a leaf name, that raises an error.
- **Types**: `int` and `decimal` become `numeric`; everything else storable becomes `text`.
  Dates and geo values are deliberately `text`, because 121's typed attributes reject the
  formats ODK produces.
- **Not created**: group nodes, attachments and ODK Collect metadata (`start`, `deviceid`,
  `instanceID`, …) are skipped entirely. The **built-in** 121 attributes 
  (`preferredLanguage`, `maxPayments`, `paymentAmountMultiplier`, `programFspConfigurationName`)
  are also skipped.
- **Forbidden**: fields named after something 121 generates (`status`, `paymentCount`,
  `registrationProgramId`, …) or the pipeline sets itself (`referenceId`) are a configuration
  mistake, so they abort the route.
- **Never updated**: an existing attribute is left untouched even if the ODK form changed its
  type; the mismatch is logged as a warning.

Because ODK's [fields endpoint](https://docs.getodk.org/central-api-form-management/#getting-form-schema-fields)
returns no question labels or choice lists, every select question
becomes a plain `text` attribute with value = raw choice name. Reading labels and choices would mean parsing the XForm definition, which is complicated and adds fragility.

Attributes required by 121 (e.g. `fullName`) are not created nor filled in with `None`: the ODK form needs those questions named exactly as 121 expects them.
121 ultimately decides, so the pipeline only raises a warning when the program marks an attribute `isRequired` (or lists it in
`fullnameNamingConvention`) and the ODK form has no field for it. 121 itself rejects what it cannot accept.

## FSP configuration

121 rejects a registration that names no FSP configuration, so every route needs one. It is not
configured, it is resolved per run from what the 121 program already has:

1. an ODK question named `programFspConfigurationName` picks one **per registration**;
2. otherwise a program with **exactly one** FSP configuration implies it, and every registration
   of the run is created with that FSP configuration;
3. a program with **none**, or with **several and no ODK question**, aborts the route with an
   error naming the configurations it found.

So a single-FSP program needs no setup at all, and a multi-FSP program only needs the extra ODK
question. Names the form supplies are checked against the program's real configurations before
anything is sent, because 121 would reject a typo it does not recognise.

Reading them needs the `program:fsp-config.read` permission. Without it a route that relies on
auto-detection fails; one whose form picks per registration continues with a warning.

## Quickstart

```bash
uv sync
cp example.env .env          # fill in ODK and 121 credentials
uv run run-pipeline --environment debug
```

The `debug` environment uses dummy submissions and writes to `output/`, so it needs no credentials.

### CLI

| Option | Purpose |
|--------|---------|
| `--environment` | `debug`, `test` or `prod` |
| `--config` | Path to the YAML config (optional) |
| `--issued-at` | Override the run timestamp (backfills) |
| `--dry-run` | Extract, transform and validate, but load nothing |
| `--verbose` | Log at DEBUG level |

Exit codes: `0` success, `1` pipeline errors, `2` config/credential error.

## Configuration

`src/odk_to_121/configs/registrations.yaml` defines, per environment, a list of **routes**, i.e.
which ODK form feeds which 121 program.

```yaml
odk:
  project_id: 1
  form_id: registration_form
121:
  program_id: 1
```

Field mappings are **not** configured; they are derived from the form.
Neither is the FSP configuration; it is [resolved from the 121 program](#fsp-configuration).
The language a person is messaged in comes from an ODK question named `preferredLanguage`;
without one, 121 falls back to English for everyone.

Secrets live in `.env` only; copy `example.env`, rename it to `.env` and fill it in.

> [!IMPORTANT]
> **Do not use admin credentials to run this pipeline.** Create a custom role with permissions
> - program.read
> - program:fsp-config.read
> - program:registration-attributes.create
> - registration.read
> - registration.create
> - registration:personal.read
>
> then create a dedicated user in 121, assign it that role, and use those credentials.

## Logging

Every run gets a `run_id`, stamped on each log line so one run can be followed end to end.

Set `APPLICATIONINSIGHTS_CONNECTION_STRING` and logs are also sent to the Log Analytics
workspace behind that Application Insights resource, via `azure-monitor-opentelemetry`. Leave it
empty (the default) and the pipeline logs to the console only, so local and CI runs send nothing.

Find a run in Log Analytics with:

```kusto
union AppTraces, AppExceptions
| where Properties.run_id == "<run_id>"
| order by TimeGenerated asc
```

Log messages never contain field values, so no personally identifiable information is stored (see the
redaction in `data_submitter.py`, which strips the answers 121 returns in its validation
errors).

## Tests

```bash
uv run pytest tests/unit/          # pure logic, no I/O
uv run pytest -m integration       # infra + end-to-end with mocked APIs
uv run ruff check . && uv run ty check
```

## AI Disclaimer

Parts of the code in this repository were written and reviewed with the assistance of AI tools, including large language models (LLMs).

All AI-generated code has been reviewed by human contributors before being merged. The humans involved take responsibility for the correctness and quality of the code.

If you have questions or concerns, please contact the maintainers.

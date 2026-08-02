# Architecture

## Who this is for

Someone comfortable with Python and SQL who has not run a scheduler or a
warehouse before.

This document explains **how the pieces fit together and why**. It does not
explain how to change any one of them — each part has its own guide:

| Guide | Covers |
| --- | --- |
| [`pipelines.md`](pipelines.md) | Extractors, loaders, DAGs |
| [`dbt.md`](dbt.md) | The model layers, schemas, testing |
| [`handoff.md`](handoff.md) | Exporting to ds-template |
| [`operations.md`](operations.md) | Containers, ports, secrets, resets |

---

## 1. The shape of the thing

Data moves in one direction through five stages, and each stage is a directory:

```text
External API
     │
     ▼
extractors/          Python — fetch, retry, return dicts
     │
     ▼
loaders/             Python — write untouched records to Postgres
     │
     ▼
PostgreSQL `raw`     Source data, every column TEXT, append-only
     │
     ▼
dbt/models/          SQL — cast, clean, join, aggregate
     │
     ├─ staging      one model per source table, lightly cleaned
     ├─ intermediate joins and business logic (ephemeral)
     └─ marts        final tables, one per question
     │
     ▼
PostgreSQL `marts`   Analysis-ready
     │
     ▼
exporters/           Python — marts to files
     │
     ▼
ds-template    Modelling, tracking, serving
```

Airflow wraps the whole column and runs it on a schedule. It is not a fifth
stage; it is the thing that presses the buttons.

## 2. Why raw data is stored untyped

`loaders/postgres_loader.py` creates every column as `TEXT`. This looks wrong
and is deliberate.

The raw layer's job is to preserve exactly what the source sent, so that a
transformation bug is recoverable by re-running dbt rather than by re-fetching
from an API that may have moved on. Casting is a decision — is this string a
date, and in which timezone? — and decisions belong in dbt's staging models
where they are visible in a diff, testable with `dbt test`, and reversible.

A loader that guesses types produces a warehouse whose failures happen at
ingestion time, in the middle of the night, with the source data already gone.

## 3. Why there are three dbt layers

**Staging** is one model per raw table: rename, cast, drop the junk. Never joins.
The rule of one-staging-model-per-source-table is what lets you find where a
column came from.

**Intermediate** is where joins and business logic live. Materialised
`ephemeral`, so these become CTEs inside the models that use them rather than
tables — they are plumbing, not products.

**Marts** are tables, one per business question. This is the only layer anything
outside dbt should read.

The layering costs you some SQL and buys you the ability to change a source
without touching a dashboard.

## 4. Configuration lives in one file

Table names, schema names, dbt directories, source registrations, and export
targets are all in `cfg/config.yaml`, read through `core/config.py`. Secrets are
in `.env`, which is never committed.

The split matters. `cfg/config.yaml` is tracked, so a change to *what the
pipeline does* shows up in code review. `.env` is not, so a change to *your
machine's credentials* does not fight with anyone else's.

`core/config.py` mirrors `src/config.py` in ds-template deliberately —
`PROJECT_ROOT` resolution, an env-var override (`DE_PROJECT_ROOT` /
`DS_PROJECT_ROOT`), `read_config()`, `project_name()` derived from the manifest.
Moving between the repositories should not mean relearning where settings live.

## 5. Why the DAG imports inside its functions

`dags/example_pipeline.py` does its `from loaders... import` inside the task
functions, not at module scope. The dag-processor re-imports every DAG file
every few seconds just to rebuild the graph. Module-scope imports make it pay
for httpx, SQLAlchemy, pyarrow, and every extractor's dependencies each time —
which shows up as DAGs that take a long time to appear after an edit.

## 6. Where this project ends

At the file `exporters/` writes. Everything after it — feature engineering,
model selection, experiment tracking, serving — belongs to
[ds-template](https://github.com/marzimin/ds-template).

The seam is a file rather than a shared database connection on purpose. A file
is a snapshot you can version, hand to someone, and reproduce a model against
six months later. A live connection makes every model run depend on the
warehouse being up and unchanged.

See [`handoff.md`](handoff.md).

## 7. Why these dependencies

| Package | Purpose | What it buys you |
| --- | --- | --- |
| `httpx` | HTTP client for extractors | Sync and async ready; mockable in tests via `pytest-httpx` |
| `tenacity` | Retries with exponential backoff | Real APIs fail intermittently; the retry is declarative |
| `pydantic` | Validates API response shapes | Pushes you toward data contracts rather than `dict` access |
| `structlog` | Structured logging | Log lines become queryable fields, not prose to grep |
| `sqlalchemy` | Database abstraction | Engine and connection lifecycle; portable across SQL databases |
| `pyarrow` | Parquet export | Typed, compressed hand-off files when CSV is not enough |
| `ruff` | Lint and format | Replaces flake8, black, and isort with one fast tool |
| `mypy` | Static type checking | Runs strict here, as in ds-template |
| `bandit` | Security linting | Catches the obvious footguns before review does |
| `pre-commit` | Runs all of the above on commit | Quality gates are automatic, and identical in CI |

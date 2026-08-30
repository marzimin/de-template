# Handing off downstream

This project owns everything up to and including the `marts` schema. A
downstream project owns everything after. The seam is a file — `exporters/`
writes it, and nothing on this side knows or cares what reads it back.

This guide walks through the reference example, [`ds-template`](https://github.com/marzimin/ds-template),
because a worked example beats an abstract one. If your downstream project
isn't ds-template, the mechanism (file format, type conversions, the
`HANDOFF_DESTINATION_DIR` env var, the two tests in "Keeping the contract
honest") still applies unchanged — only the specifics under "Setup" and
"Declaring the columns" (ds-template's own directory layout, config keys, and
`FEATURE_COLUMNS`) are particular to that one project.

---

## Why a file rather than a shared connection

A file is a snapshot. You can version it, hand it to a colleague, and reproduce
a model against it six months later. A live database connection makes every
training run depend on the warehouse being up, reachable, and unchanged — and
makes "the model got worse" impossible to distinguish from "someone edited a
staging model".

The cost is freshness, which is the right trade for modelling work and the wrong
one for a dashboard. Point dashboards at `marts` directly.

---

## See it work first

```bash
make demo-handoff
```

That builds two marts in a throwaway Postgres, exports both, and checks the
results — no setup, and nothing touched in either project. One mart carries
every awkward type (`uuid`, `jsonb`, arrays, `bytea`, `interval`) to prove the
export is *faithful*; the other is training-shaped to prove it is *usable*.

The distinction is the lesson: a mart that round-trips correctly is not
automatically one a model can consume. ds-template needs numeric features
with no missing values, so identifiers, timestamps and JSON blobs still have to
be cast, encoded, or dropped — in dbt, where the decision is visible.

## Setup

Both repositories checked out side by side:

```text
~/code/
├── de-template/            ← this project
└── ds-template/      ← the DS project
```

Set the destination in this project's `.env`:

```bash
HANDOFF_DESTINATION_DIR=/Users/you/code/ds-template/data/raw
```

Declare what to export in `cfg/config.yaml`:

```yaml
exports:
  destination: "data/exports"     # used when HANDOFF_DESTINATION_DIR is unset
  format: "csv"
  datasets:
    - relation: "marts.example_items"
      file_name: "example_items.csv"
```

Then:

```bash
make export
```

Over in the DS project, name the file in its `cfg/config.yaml`:

```yaml
data:
  raw_dir: "data/raw"
  input_file: "example_items.csv"

target_column: "ITEM_NAME_LENGTH"
```

Run `make pipeline` there and it picks the file up.

---

## The column-name convention

The two projects normalise column names in opposite directions, and this is
fine:

| Stage | Convention | Example |
| --- | --- | --- |
| Source API | whatever it sends | `Item Name Length` |
| This project's loader | `lower_snake` | `item_name_length` |
| Exported file | `lower_snake` | `item_name_length` |
| ds-template, on read | `UPPER_SNAKE` | `ITEM_NAME_LENGTH` |

The DS project re-normalises on read, so the round trip is lossless. What it
means in practice: **`target_column` over there must be written in upper case**,
even though the file's header is lower case. Getting this wrong produces a
"target column not found" error naming a column you can plainly see in the CSV.

---

## Running it as a DAG task

`dags/example_pipeline.py` already ends with an `export_marts` task:

```text
extract_and_load → dbt_run → export_marts
```

For Airflow to write into the DS project, the container needs that directory
mounted. In `docker-compose.yml`, replace the `data/exports` mount:

```yaml
    - /Users/you/code/ds-template/data/raw:/opt/airflow/data/exports
```

The compose file already sets `HANDOFF_DESTINATION_DIR=/opt/airflow/data/exports`, so
nothing else changes. Restart with `make up`.

---

## How types survive the trip

CSV holds only text, so every value the database returns has to become a string.
Left to itself Python's `csv` module calls `str()`, which is wrong for half the
types a dbt mart can produce — `str()` on a binary column gives
`<memory at 0x7f3c...>`, losing the bytes *and* changing between runs, so two
exports of identical data diff as changed.

`exporters/serialisation.py` decides these conversions explicitly:

| Postgres type | In the CSV | Read it back with |
| --- | --- | --- |
| `integer`, `double precision` | `42`, `3.14159` | as-is |
| `numeric` | `1234.5678` — full precision, not the float | `Decimal(...)` |
| `boolean` | `True` / `False` | pandas gives a real `bool` dtype |
| `text` | quoted when it contains `,` `"` or newlines | as-is |
| `date`, `timestamp`, `timestamptz` | ISO 8601, e.g. `2024-03-01T12:34:56+00:00` | `pd.to_datetime` |
| `interval` | ISO 8601 duration, `P1DT2H3M4S` | `pd.Timedelta` / `isodate` |
| `uuid` | `11111111-2222-...` | `UUID(...)` |
| `jsonb` | valid JSON with double quotes | `json.loads` |
| arrays | valid JSON, `[1, 2, 3]` | `json.loads` |
| `bytea` | lowercase hex, `deadbeef` | `bytes.fromhex(...)` |
| `NULL` | empty (configurable) | pandas gives `NaN` |

`tests/test_exporters/test_postgres_types.py` asserts each row of that table
against a real Postgres. Run it with `make test-integration`.

### NULL versus empty string

Both are written as an empty field by default, and pandas reads both as `NaN`.
That is deliberate — it is what ds-template expects with no extra
configuration. If you need to tell them apart, set a sentinel:

```yaml
exports:
  null_sentinel: "\\N"
```

and pass `na_values=["\\N"]` on the reading side.

## CSV or Parquet

`exports.format` accepts both.

**Use CSV** unless you have a reason not to. ds-template reads CSV out of
the box.

**Use Parquet** when the mart is large, or when you want types carried in the
file rather than re-inferred from text — `numeric` stays `decimal128`, dates
stay `date32`, `bytea` stays `binary`. Two caveats: the exporter buffers the
whole relation in memory for Parquet (see the docstring on `_write_parquet`),
and JSON columns are stored as JSON text rather than Arrow structs, because
struct inference is built from the first rows and fails on a later row with
different keys.

---

## Keeping the contract honest

Two tests guard the seam:

- **`tests/test_exporters/test_cli.py`** checks every exported relation has a
  dbt model building it. Delete a mart without updating `cfg/config.yaml` and
  the build fails.
- **`tests/test_core/test_config.py`** checks the schema names in
  `cfg/config.yaml` match the `+schema:` settings in `dbt/dbt_project.yml`.

Neither can check the DS project's `cfg/config.yaml`, since it is a separate
repository. If you rename an exported file, update `data.input_file` there too.

### Declaring the columns

`dbt/models/marts/schema.yml` describes every exported mart column with
`not_null` / `unique` tests. That file is the contract on this side — a mart
that violates it fails `make dbt-test` before the export runs.

To close the loop, mirror those constraints as Pandera checks in the DS
project's `FEATURE_COLUMNS`, remembering the upper-case column names:

```python
# ds-template: backend/src/schemas.py
FEATURE_COLUMNS = {
    "ITEM_ID": Column(int, checks=Check.ge(0)),
    "ITEM_NAME_LENGTH": Column(int, checks=Check.ge(0)),
}
```

The same violation then fails from both sides — here when dbt builds the table,
there when the file is read.

---

## Where modelling does *not* belong

This project has no `ml` dependency group and no MLflow. Feature engineering in
SQL is fine and belongs in `dbt/models/`; anything that fits or scores a model
belongs in ds-template, where the experiment tracking lives.

`uv sync --group notebooks` gives you Jupyter and pandas here for exploring the
warehouse — that is exploration, not modelling.

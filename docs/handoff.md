# Hand-off to ds-template-local

This project owns everything up to and including the `marts` schema.
[`ds-template-local`](https://github.com/marzimin/ds-template-local) owns
everything after. The seam is a file.

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

## Setup

Both repositories checked out side by side:

```text
~/code/
├── de-template/            ← this project
└── ds-template-local/      ← the DS project
```

Set the destination in this project's `.env`:

```bash
DS_DATA_RAW_DIR=/Users/you/code/ds-template-local/data/raw
```

Declare what to export in `cfg/config.yaml`:

```yaml
exports:
  destination: "data/exports"     # used when DS_DATA_RAW_DIR is unset
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
| ds-template-local, on read | `UPPER_SNAKE` | `ITEM_NAME_LENGTH` |

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
    - /Users/you/code/ds-template-local/data/raw:/opt/airflow/data/exports
```

The compose file already sets `DS_DATA_RAW_DIR=/opt/airflow/data/exports`, so
nothing else changes. Restart with `make up`.

---

## CSV or Parquet

`exports.format` accepts both.

**Use CSV** unless you have a reason not to. ds-template-local reads CSV out of
the box.

**Use Parquet** when the mart is large, or when types matter enough that you do
not want the DS side re-inferring them from strings. Note that the exporter
buffers the whole relation in memory for Parquet — see the docstring on
`_write_parquet` for why, and what to change if your mart does not fit.

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

A stronger contract, if the pairing becomes load-bearing: declare the mart's
columns in `dbt/models/marts/schema.yml` with `not_null`/`unique` tests, and
mirror them as a Pandera schema in the DS project's `FEATURE_COLUMNS`. The two
then fail on the same violation from opposite sides.

---

## Where modelling does *not* belong

This project has no `ml` dependency group and no MLflow. Feature engineering in
SQL is fine and belongs in `dbt/models/`; anything that fits or scores a model
belongs in ds-template-local, where the experiment tracking lives.

`uv sync --group notebooks` gives you Jupyter and pandas here for exploring the
warehouse — that is exploration, not modelling.

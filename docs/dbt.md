# dbt

Writing and running the SQL transformation layer.

---

## The three layers

| Layer | Folder | Materialised | Purpose |
| --- | --- | --- | --- |
| Staging | `dbt/models/staging/` | view | One model per raw table. Rename, cast, filter. Never joins. |
| Intermediate | `dbt/models/intermediate/` | ephemeral | Joins and business logic. Becomes a CTE, not a table. |
| Marts | `dbt/models/marts/` | table | Final tables, one per business question. |

Only marts are read from outside dbt. The layering is explained in
[`architecture.md`](architecture.md#3-why-there-are-three-dbt-layers).

To add a model, drop a `.sql` file in the right folder. dbt discovers it.

---

## Schemas

Models land in exactly the schema named by their `+schema:` setting in
`dbt/dbt_project.yml`. That is not dbt's default behaviour — it normally
*concatenates* the target schema with the custom one, so target `staging` plus
custom `marts` gives you `staging_marts`. `dbt/macros/generate_schema_name.sql`
overrides that.

Three files have to agree on the schema names:

1. `cfg/config.yaml` — `warehouse:`
2. `dbt/dbt_project.yml` — the `+schema:` settings
3. `docker/postgres/init.sh` — which schemas get created and granted

`tests/test_core/test_config.py` checks that the first two agree. The third only
runs on a fresh volume, so if you change it, `make reset`.

---

## Running dbt

**Inside the Airflow container**, where the environment is already set:

```bash
make dbt-run-container
```

**From your laptop**, which needs `.env` loaded first:

```bash
make dbt-run
make dbt-test
```

Both read the connection from `WAREHOUSE_USER`, `WAREHOUSE_PASSWORD`,
`WAREHOUSE_DB`, `POSTGRES_HOST` and `POSTGRES_PORT` via `dbt/profiles.yml` —
the same variables the Python loader uses, so both connect as the same role.

---

## Testing models

Column tests go in a `schema.yml` next to the models:

```yaml
version: 2

models:
  - name: stg_stripe_charges
    description: One row per charge, cast and cleaned.
    columns:
      - name: charge_id
        tests: [not_null, unique]
```

Bespoke assertions go in `dbt/tests/` as SQL that returns the *offending* rows —
zero rows means the test passed. See
`dbt/tests/assert_example_items_not_empty.sql`.

Run them with `make dbt-test`.

---

## Renaming the project

Three values must agree, all using underscores rather than hyphens:

1. `dbt/dbt_project.yml` — `name:` and `profile:`
2. `dbt/profiles.yml` — the top-level key
3. `dbt/dbt_project.yml` — the key under `models:`

`pyproject.toml`'s `name` is separate and may use hyphens.

---

## Exporting a mart

Marts named under `exports.datasets` in `cfg/config.yaml` are written to files
by `make export`. `tests/test_exporters/test_cli.py` checks that every exported
relation has a dbt model actually building it, so deleting a mart without
updating the config fails the build.

See [`handoff.md`](handoff.md).

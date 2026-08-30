# Pipelines

Writing extractors, loaders, and DAGs.

---

## The daily loop

```text
1. Copy extractors/api/example_api.py → extractors/api/my_source.py
      ↓ change BASE_URL, implement extract()
2. Add the API key to .env       (MY_SOURCE_API_KEY=...)
3. Register it in cfg/config.yaml under `sources:`
4. Write tests → tests/test_extractors/test_my_source.py
      ↓ make test
5. Point a DAG at it → dags/my_pipeline.py
      ↓ appears in the UI within ~1 min; the dag-processor picks it up
6. Inspect the raw table with SQLTools (database: warehouse)
7. Write the dbt models → see docs/dbt.md
8. Commit → hooks lint → push → CI runs the same checks
```

---

## Extractors

Subclass `BaseExtractor` and implement `extract`, returning a flat list of
dicts — one per record.

```python
class StripeExtractor(BaseExtractor):
    BASE_URL = "https://api.stripe.com/v1"

    def __init__(self) -> None:
        self.api_key = os.environ["STRIPE_API_KEY"]
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30
        )

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _get(self, path: str) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.BASE_URL}{path}")
        response.raise_for_status()
        return response.json()

    def extract(self) -> list[dict[str, Any]]:
        return self._get("/charges")
```

Three things the example gets right and yours should too:

- **Read the key in `__init__`, not at module scope.** A missing key then fails
  when the task runs, with a task-level error, rather than breaking DAG parsing
  for every pipeline in the repository.
- **Put the retry on the request method, not on `extract`.** Retrying `extract`
  re-runs pagination from the beginning.
- **Return dicts, not models.** Validation belongs in the staging layer where it
  is visible; the loader squares up ragged keys for you.

### Registering a source

```yaml
# cfg/config.yaml
sources:
  stripe_charges:
    extractor: "extractors.api.stripe_api:StripeExtractor"
    target_table: "raw.stripe_charges"
```

The `module:ClassName` string is resolved at run time by `core/imports.py`, so
nothing has to import your extractor to know about it. `tests/test_core/
test_imports.py` checks every registered path actually resolves, so a typo here
fails the build rather than a 3am task.

---

## Loaders

`PostgresLoader` handles the common case: append records to a table in `raw`,
creating the schema and table if they do not exist.

```python
PostgresLoader().load(records, table="raw.stripe_charges")
```

What it does for you:

- **Normalises column names** to lowercase identifiers — `Order ID` becomes
  `order_id`, `created-at` becomes `created_at`.
- **Squares up ragged records.** Keys missing from some records become NULL, so
  one multi-row INSERT works.
- **Rejects collisions.** If `Order ID` and `order-id` both normalise to
  `order_id`, it raises rather than silently dropping one.
- **Validates identifiers.** Schema and table names are interpolated into DDL,
  where bind parameters are not available, so they are checked against a strict
  pattern instead.

Every column is created `TEXT`. That is deliberate — see
[`architecture.md`](architecture.md#2-why-raw-data-is-stored-untyped).

### Load modes, and idempotency

`load` has no upsert. Running a pipeline twice in the default `append` mode
loads the data twice. Two ways to deal with that:

**Deduplicate in staging** — usually the better answer. `raw` keeps the full
history, and the choice of which row wins stays visible in SQL:

```sql
with ranked as (
    select *, row_number() over (
        partition by id order by updated_at desc
    ) as row_num
    from {{ source('raw', 'my_source') }}
)
select id as item_id, trim(name) as item_name
from ranked
where row_num = 1
```

**Or replace the table** — for small sources you re-fetch in full each run,
where a snapshot is simpler than a history:

```yaml
# cfg/config.yaml
sources:
  my_source:
    extractor: "extractors.api.my_source:MySourceExtractor"
    target_table: "raw.my_source"
    load_mode: "replace"     # default is "append"
```

The delete and the insert run in one transaction, so a failed insert cannot
leave you with an empty table. An **empty extract is always a no-op**, in both
modes — otherwise a transient API failure returning `[]` would wipe the table
and the next dbt run would build marts from nothing.

---

## Local dummy data (no external services)

`extractors/files/local_excel.py` reads Excel workbooks out of
`data/sample_source/` — no network call, no external account. It exists to
exercise the whole pipeline (`extract → load → dbt → export`) immediately
after cloning, and as a template for a real file- or API-backed extractor
later. It ships four extractor classes, one per file-naming pattern, each
needing a different `load_mode` — see that module's docstring for the seed /
snapshot / incremental distinction.

```bash
make local-seed     # writes fake orders/customers/sales into data/sample_source/
```

The fake-data generation is split in two, on purpose:

| File | What's in it | Replace it? |
| --- | --- | --- |
| `scripts/seed_toolkit.py` | Generic primitives — one function per file kind (`write_static_workbook`, `write_overwritten_snapshot`, `write_appended_snapshot`, `write_incremental_partitions`). Knows nothing about orders or customers. | No — keep this |
| `scripts/demo_dataset.py` | The shipped example's actual content — categories, regions, orders, customers, monthly sales, each written with one `seed_toolkit` call. | **Yes — this is what to edit** |

`scripts/seed_local_dummy_data.py` is just the CLI wrapper around
`demo_dataset.seed_all()`; it doesn't change when you replace the dataset.
Nothing in `.env` is required to run any of this: the destination is
`local_dummy_data.destination` in `cfg/config.yaml`, not a secret.

```yaml
# cfg/config.yaml
sources:
  local_seed_data:
    extractor: "extractors.files.local_excel:LocalSeedExtractor"
    target_table: "raw.local_seed_data"
    load_mode: "replace"
```

This is demo/testing data, not a production source. Two ways to move past it:

- **Swap in a real API.** Treat `extractors/api/example_api.py` as the pattern
  (see "Extractors" above), and delete `extractors/files/`,
  `scripts/demo_dataset.py`, `scripts/seed_toolkit.py`, and the `local_*`
  entries in `cfg/config.yaml`.
- **Keep the local-file shape, swap the content.** `scripts/demo_dataset.py`'s
  own docstring has the checklist: define your fake entities there using
  `seed_toolkit`'s four primitives, copy the matching extractor class in
  `extractors/files/local_excel.py` (a few lines each), and add the
  `local_*`-shaped source entry. `seed_toolkit.py`, `core/local_files.py`, and
  `extractors/files/local_excel.py`'s base class don't need to change.

A few things worth knowing before leaning on the local data for anything
beyond structural testing:

- **`_source_modified` is filesystem mtime, not an edit history.** It is
  stamped from the seeded file's mtime, which a fresh `git clone` or CI
  checkout does not preserve. Don't build a "did the source actually change"
  check that depends on this value being stable across environments.
- **No real change-detection story.** `latest_orders.xlsx` and
  `customers.xlsx` are `load_mode: replace` because the extractor re-reads
  the *whole current file* every run — nothing here tracks staleness or
  diffs the previous load. See "Load modes, and idempotency" above for the
  general pattern. A dbt snapshot (`dbt/snapshots/`, already configured in
  `dbt_project.yml` but empty) is the idiomatic way to get real change
  history out of a replace-mode raw table — track it with a `check` strategy
  on the staging model's natural key, not by trusting `_source_modified`.
- **It's a fixture generator, not a fixture.** Re-running `make local-seed`
  advances `latest_orders.xlsx`, grows `customers.xlsx`, and — once a
  month — adds a new `monthly_sales_*.xlsx`. If a test needs a fixed,
  unchanging dataset, seed once and stop re-running it, or write directly
  into `data/sample_source/` with your own fixture instead.

---

## DAGs

Copy `dags/example_pipeline.py`. It runs extract → dbt → export and reads
everything it needs from `cfg/config.yaml`.

```python
SOURCE_NAME = "stripe_charges"  # the key you added under `sources:`
```

**Import inside the task functions, not at module scope.** The dag-processor
re-imports every DAG file every few seconds. See
[`architecture.md`](architecture.md#5-why-the-dag-imports-inside-its-functions).

**Annotate the callables.** `mypy` runs strict over `dags/`, and a bare
`def my_task():` will fail the hooks.

### Testing a DAG

`tests/test_dags.py` loads every file in `dags/` through a `DagBag` and asserts
there are no import errors. A DAG that fails to parse does not error loudly —
it just never appears in the UI, and you find out when the data does not arrive.

```bash
make test
```

To check one file quickly without the suite:

```bash
uv run python dags/my_pipeline.py   # no output means it parsed
```

---

## What triggers a rebuild vs. a restart vs. nothing

| You changed | Action needed |
| --- | --- |
| A `.py` file in `dags/`, `core/`, `extractors/`, `loaders/`, `exporters/` | Nothing — bind-mounted |
| A `.sql` file in `dbt/models/` | Nothing — re-run dbt |
| `cfg/config.yaml` | Nothing — read at task run time |
| `requirements-airflow.txt` | `make build` then `make up` |
| `docker-compose.yml` | `make up` |
| `docker/postgres/init.sh` | `make reset` — **deletes local data** |

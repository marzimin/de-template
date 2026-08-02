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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
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

### It appends, it does not upsert

`load` has no deduplication. Running a pipeline twice loads the data twice.
For the shipped daily schedule with a full-refresh mart that is harmless, but
if you need idempotency you have two options:

- **Truncate first**, for small tables you re-fetch in full.
- **Deduplicate in staging**, keeping the newest row per key with a window
  function. This is usually the better answer: it preserves history in `raw` and
  keeps the decision visible in SQL.

---

## DAGs

Copy `dags/example_pipeline.py`. It runs extract → dbt → export and reads
everything it needs from `cfg/config.yaml`.

```python
SOURCE_NAME = "stripe_charges"   # the key you added under `sources:`
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

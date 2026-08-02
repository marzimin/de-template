# DE Template

A starting point for data engineering projects: a warehouse, a scheduler, and a
transformation layer running on your laptop, with a defined hand-off to the
modelling work downstream.

```text
cfg/config.yaml   ← configure your sources, schemas, and exports here
extractors/       ← Python: pull data from APIs
loaders/          ← Python: write raw records to Postgres
dbt/              ← SQL: raw → staging → intermediate → marts
exporters/        ← Python: marts → files for the DS project
dags/             ← Airflow: run all of the above on a schedule
```

In most cases you edit the first one and add a file to the second.

---

## Quick start

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/),
[uv](https://docs.astral.sh/uv/) (`brew install uv`), and Git.

```bash
make setup
```

That copies `.env.example` to `.env`, installs the Python environment and git
hooks, builds the Airflow image, initialises the metadata database, and starts
every service.

Then open **<http://localhost:8080>** and sign in with `admin` / `admin`.

```bash
make help    # every command, with a description
```

---

## What you get

Four containers and a warehouse:

| Service | Port | What it does |
| --- | --- | --- |
| `postgres` | 5432 | The warehouse. Three schemas — `raw`, `staging`, `marts` — created on first start |
| `airflow-api-server` | 8080 | The UI and REST API (replaces `webserver` from Airflow 2) |
| `airflow-scheduler` | — | Decides what runs when |
| `airflow-dag-processor` | — | Parses your DAG files; separate and required in Airflow 3 |

And a worked example that runs end to end: `example_pipeline` extracts from an
API, loads to `raw`, builds three dbt models, and exports the mart to a file.

> **The bundled example points at a placeholder API.** Its `extract_and_load`
> task is *expected* to fail until you swap in a real source and key. The DAG
> still parses and appears in the UI. Use it as a copy-paste starting point,
> then delete it.

---

## Adding your first data source

1. **Copy the example extractor.** Duplicate `extractors/api/example_api.py`,
   rename it for your source, change `BASE_URL`, and make `extract` return a
   flat list of dicts.

2. **Add your API key** to `.env`, and read it with `os.environ["..."]`.

3. **Register it in `cfg/config.yaml`:**

   ```yaml
   sources:
     stripe_charges:
       extractor: "extractors.api.stripe_api:StripeExtractor"
       target_table: "raw.stripe_charges"
   ```

4. **Point a DAG at it** — copy `dags/example_pipeline.py` and set
   `SOURCE_NAME` to the key you just added.

5. **If you added a Python package,** put it in *both* `pyproject.toml` and
   `requirements-airflow.txt`, then `make build`. A test enforces that the two
   agree, so you cannot forget one.

`dags/`, `core/`, `extractors/`, `loaders/`, `exporters/`, `cfg/` and `dbt/` are
all bind-mounted, so edits to existing files are picked up within a minute — no
restart needed.

---

## Handing data to the DS project

This template stops at the `marts` schema. [`ds-template-local`](https://github.com/marzimin/ds-template-local)
picks up from a file. `exporters/` is the seam:

```bash
make export
```

Set `DS_DATA_RAW_DIR` in `.env` to that project's `data/raw/` and the files land
where it already looks for them. See [`docs/handoff.md`](docs/handoff.md) for the
full setup, including running it as the last task of a DAG.

---

## Commands

```bash
make setup      # install everything and start the stack
make up         # start services      make down     # stop them
make logs       # follow the logs     make reset    # wipe and start fresh
make dbt-run    # build the models    make dbt-test # test them
make export     # write marts out for the DS project
make test       # run the test suite
make lint       # run every pre-commit hook
make help       # every target
```

---

## Documentation

| Document | Read it when |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | You want to understand how the pieces fit together and why |
| [`docs/pipelines.md`](docs/pipelines.md) | You are writing extractors, loaders, or DAGs |
| [`docs/dbt.md`](docs/dbt.md) | You are writing SQL models |
| [`docs/handoff.md`](docs/handoff.md) | You are wiring this project into ds-template-local |
| [`docs/operations.md`](docs/operations.md) | You are managing the containers, ports, or secrets |

---

## When something looks wrong

| Symptom | Likely cause | Try |
| --- | --- | --- |
| Containers will not start | Docker Desktop is not running | Check the whale icon; run `docker info` |
| Port 5432 or 8080 in use | Something else has it | `lsof -i :5432`, or change the mapping in `docker-compose.yml` |
| `uv: command not found` | Shell has not reloaded | Reopen the terminal, or `source ~/.zshrc` |
| Airflow shows no DAGs | The file failed to parse | `docker compose logs airflow-dag-processor`, or run `make test` — `tests/test_dags.py` catches this |
| A task fails with `ModuleNotFoundError` | Package missing from the image | Add it to `requirements-airflow.txt` and `make build` |
| UI does not load, containers restarting | A typo in an `AIRFLOW__…` setting | `docker compose ps`, then `docker compose logs airflow-api-server` |
| `permission denied for schema public` on init | Volume predates the `init.sh` fix | `make reset` (deletes local data) |
| `make export` writes nowhere useful | `DS_DATA_RAW_DIR` unset | Set it in `.env`, or collect the files from `data/exports/` |
| Commit fails with `pre-commit not found` | Hook points at a deleted virtualenv | `make hooks` |

---

## Making it your own

- **Rename the project.** Three values must agree: `name` in `pyproject.toml`,
  and `name` + `profile` in `dbt/dbt_project.yml` (underscores, no hyphens),
  matched by the top-level key in `dbt/profiles.yml`.
- **Change the schemas.** Edit `warehouse:` in `cfg/config.yaml`, the `+schema:`
  settings in `dbt/dbt_project.yml`, and `docker/postgres/init.sh`. A test
  checks the first two agree.
- **Explore the data.** `uv sync --group notebooks` adds Jupyter and pandas,
  pointed at the same warehouse. Modelling belongs in `ds-template-local`.
- **Quality gates.** `make lint` runs Ruff, MyPy (strict), Bandit, and the
  standard file hygiene hooks. The same checks run in CI.

# Operations

Running the containers day to day.

---

## The services

Two containers:

| Service | Port | Role |
| --- | --- | --- |
| `postgres` | 5432 | The warehouse, plus Airflow's own metadata database |
| `airflow` | 8080 | Everything Airflow — see below |

`airflow` runs `airflow standalone` — Airflow's own built-in local-dev mode,
not a custom script. One command starts the API server (UI + REST API,
replaces `webserver` from Airflow 2), the scheduler (also executes tasks,
under `LocalExecutor`), the DAG processor (parses DAG files — a separate
*process* in Airflow 3, but not a separate *container* here), and the
triggerer (deferred/sensor-style tasks — absent from this template until this
change, since nothing previously ran it). Log lines are prefixed by which of
the four they came from (`scheduler |`, `api-server |`, etc.) so you can still
tell them apart in `docker compose logs`.

This works cleanly here specifically because `standalone` forces
`LocalExecutor` and `SimpleAuthManager` if they aren't already set — this
template hardcodes both anyway (see "Login" and `docker-compose.yml`), so
nothing about the configuration changes versus running the four pieces
separately. It also means there's no separate init step: `standalone`
initialises the metadata database itself, idempotently, on every start.

A real multi-node deployment (`CeleryExecutor`/`KubernetesExecutor`, secrets
in a real backend, `FAB`/`Keycloak` auth) would go back to separate
containers per component — the split this collapses is a *process*
architecture, not just a container-count optimisation, and Airflow itself
prints a warning about exactly that trade-off (`SimpleAuthManager is active
but the deployment shape looks like production...`) since it can't tell "one
laptop" from "one very small production deployment" apart from the outside.
That warning is expected and safe to ignore here.

---

## Commands

```bash
make up       # start everything in the background
make down     # stop, preserving data
make logs     # follow all logs
make build    # rebuild the image after a requirements change
make reset    # down -v, up --build — DELETES ALL LOCAL DATA
```

For the Airflow logs, or one component's slice of them:

```bash
docker compose logs airflow
docker compose logs airflow | grep '^airflow-1  | scheduler'
docker compose ps               # which containers are actually up
```

Health check (reports all four components, since `standalone` runs them all):

```bash
curl http://localhost:8080/api/v2/monitor/health
```

---

## First-time initialisation

`make setup` does this for you. If you are doing it by hand:

```bash
docker compose up -d --build
```

No separate init step — `standalone` runs the metadata-table migration itself
on every start, before serving. `init.sh` in `docker/postgres/` runs
**only on an empty volume**. It creates the `airflow_db` metadata database,
the warehouse database and role, and the `raw` / `staging` / `marts` schemas.
Changing it means `make reset`.

---

## Login

Airflow 3 removed the FAB-based `airflow users` CLI from core. This template
uses the built-in *SimpleAuthManager* with a pre-seeded password file
(`docker/airflow/simple_auth_manager_passwords.json`), so the login is a stable
`admin` / `admin` rather than a random password printed once into the logs.

**This is for local development only.**

---

## Secrets

`docker-compose.yml` contains three development placeholders:

```yaml
AIRFLOW__CORE__FERNET_KEY: ""                        # disables encryption
AIRFLOW__API_AUTH__JWT_SECRET: "dev-jwt-secret-change-me"
AIRFLOW__API__SECRET_KEY: "dev-secret-key-change-me"
```

All three must change before this runs anywhere shared. Generate a Fernet key
with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The JWT secret must match across services — `LocalExecutor` tasks are run by the
scheduler and authenticate to the api-server's execution API with it.

Real secrets belong in `.env`, which is gitignored. Non-secret configuration
belongs in `cfg/config.yaml`, which is tracked.

---

## Connecting to the warehouse

VS Code with the SQLTools extension (already in
`.vscode/extensions.json`), or any client:

| Setting | Value |
| --- | --- |
| Host | `localhost` |
| Port | `5432` |
| Database | `warehouse` |
| User | `de_user` |
| Password | `de_password` |

These come from `.env`. Inside the containers the host is `postgres`, not
`localhost` — `docker-compose.yml` overrides `POSTGRES_HOST` for exactly this
reason.

---

## Upgrading the pinned versions

`POSTGRES_VERSION` and `AIRFLOW_VERSION` in `.env` (defaults: `17` and `3.3.1`,
also baked into `docker-compose.yml`/`docker/airflow/Dockerfile` as fallbacks
so this works even before `.env` exists) are the only places these versions
are pinned. Bump one, then:

```bash
make build   # rebuild the Airflow image against the new AIRFLOW_VERSION
make up      # or: make reset, if POSTGRES_VERSION changed — see below
make test    # dags/, extractors/, everything still parses and passes
```

**Airflow**: same-major bumps (3.x → 3.y) are usually additive, but this
template already tracks several Airflow-3-specific behaviours (the
dag-processor split, SimpleAuthManager, the task SDK — see "The services"
above and `architecture.md`), and the 3.0→3.3 line has had real breaking
changes between minors. Treat a bump as needing the checklist above, not as a
trivial tag change — and check `requirements-airflow.txt`'s provider package
floors still resolve against the new core version.

**Postgres**: the client side (`psycopg2-binary`, SQLAlchemy) and this
project's own SQL are not version-sensitive — the risk is entirely the
`postgres_data` volume. A major-version image swap does not upgrade an
existing volume's on-disk format in place; Postgres will refuse to start
against it. For local dev, `make reset` sidesteps this by starting from an
empty volume. For anything with data you'd miss, that means a real
`pg_upgrade` or dump/restore, not a tag bump.

**dbt**: deliberately *not* wired the same way. `pyproject.toml` and
`requirements-airflow.txt` pin `dbt-core<2.0.0` and `dbt-postgres<1.10.0` —
dbt shipped a rewritten "Fusion" engine (`dbt-core` 2.x) that, as of this
writing, has no Postgres adapter at all. `dbt-postgres` releases past 1.9.x
require it. An unpinned resolve picks the newest version regardless of
whether it works, so — unlike Postgres/Airflow above — there is no env var
here to bump; move the pin only once Fusion's Postgres adapter exists and is
out of beta, and re-test `dbt parse`/`dbt run` before trusting it.

---

## The published image

`.github/workflows/build.yml` bumps an integer tag (`v1`, `v2`, …) on every push
to `main` and pushes the Airflow image to `ghcr.io/<owner>/<repo>`. The image
bakes in the project source, so it runs standalone; under compose those paths
are shadowed by bind mounts, which is what makes local edits take effect without
a rebuild.

To publish somewhere else, change the login and tag steps in that workflow.

---

## CI

Three workflows, matching ds-template:

| Workflow | Runs | On |
| --- | --- | --- |
| `pre-commit.yaml` | Every hook, all files | Every branch and PR |
| `tests.yaml` | pytest, uploads a junit report | Every branch and PR |
| `build.yml` | Tag bump, image build and push | Pushes to `main` |

Lint, format, and type checks live **only** in the pre-commit workflow, driven
by the same `.pre-commit-config.yaml` you get locally. Duplicating them as
separate CI steps lets the two drift.

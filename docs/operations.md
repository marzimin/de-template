# Operations

Running the containers day to day.

---

## The services

| Service | Port | Role |
| --- | --- | --- |
| `postgres` | 5432 | The warehouse, plus Airflow's own metadata database |
| `airflow-api-server` | 8080 | UI and REST API — replaces `webserver` from Airflow 2 |
| `airflow-scheduler` | — | Decides what runs when; also executes tasks under `LocalExecutor` |
| `airflow-dag-processor` | — | Parses DAG files. Separate and required in Airflow 3 |
| `airflow-init` | — | Runs once to create the metadata tables, then exits |

---

## Commands

```bash
make up       # start everything in the background
make down     # stop, preserving data
make logs     # follow all logs
make build    # rebuild the image after a requirements change
make reset    # down -v, re-init, up — DELETES ALL LOCAL DATA
```

For one service's logs:

```bash
docker compose logs airflow-scheduler
docker compose ps               # which containers are actually up
```

Health check:

```bash
curl http://localhost:8080/api/v2/monitor/health
```

---

## First-time initialisation

`make setup` does this for you. If you are doing it by hand, the order matters:

```bash
docker compose up airflow-init --build   # wait for "Database migrating done!"
docker compose up -d
```

`init.sh` in `docker/postgres/` runs **only on an empty volume**. It creates the
`airflow_db` metadata database, the warehouse database and role, and the `raw` /
`staging` / `marts` schemas. Changing it means `make reset`.

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

## The published image

`.github/workflows/build.yml` bumps an integer tag (`v1`, `v2`, …) on every push
to `main` and pushes the Airflow image to `ghcr.io/<owner>/<repo>`. The image
bakes in the project source, so it runs standalone; under compose those paths
are shadowed by bind mounts, which is what makes local edits take effect without
a rebuild.

To publish somewhere else, change the login and tag steps in that workflow.

---

## CI

Three workflows, matching ds-template-local:

| Workflow | Runs | On |
| --- | --- | --- |
| `pre-commit.yaml` | Every hook, all files | Every branch and PR |
| `tests.yaml` | pytest, uploads a junit report | Every branch and PR |
| `build.yml` | Tag bump, image build and push | Pushes to `main` |

Lint, format, and type checks live **only** in the pre-commit workflow, driven
by the same `.pre-commit-config.yaml` you get locally. Duplicating them as
separate CI steps lets the two drift.

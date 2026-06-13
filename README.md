# Data Engineering Template

A ready-to-use starting point for data engineering and analytics projects. Clone this repository, follow the setup steps below, and you will have a fully working local environment — with a database, a pipeline scheduler, and a data transformation layer — running on your Mac in under an hour.

---

## What is this?

This template wires together four industry-standard tools so you do not have to do it yourself:

| Tool | What it does |
| --- | --- |
| **Docker Desktop** | Runs your database and scheduler as isolated services on your laptop |
| **PostgreSQL 16** | The database where your raw and processed data lives |
| **Apache Airflow 3** | The scheduler that runs your data pipelines on a timetable |
| **dbt** | Cleans and transforms raw data into analysis-ready tables |

Your Python code (the part that fetches data from APIs and loads it into the database) lives in the `extractors/` and `loaders/` folders. Everything else is plumbing that this template handles for you.

---

## How data flows through the system

```text
External API
     |
     v
extractors/          <-- your Python code fetches data here
     |
     v
loaders/             <-- loads raw data into the database
     |
     v
PostgreSQL (raw)     <-- untouched source data
     |
     v
dbt models           <-- cleans and reshapes the data
     |
     v
PostgreSQL (marts)   <-- final tables ready for analysis or dashboards
     |
     v
Airflow DAG          <-- runs all of the above steps on a schedule
```

---

## First steps after cloning this template

Once you have created your own repository from this template, rename the project in three places before doing anything else:

1. **`pyproject.toml`** — change `name = "de-template"` to your project name.

2. **`dbt/dbt_project.yml`** — change `name: 'de_template'` and `profile: 'de_template'` to match (use underscores, no hyphens).

3. **`dbt/profiles.yml`** — change the top-level key `de_template:` to the same name you used in step 2.

These three values must be consistent. Everything else (Docker, Python packages, CI) works without renaming.

---

## Before you start

You will need the following installed on your Mac. Each link goes to the official download or install page.

1. **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
   After installing, open the app and make sure the whale icon appears in your menu bar.

2. **Homebrew** — open Terminal and run:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

3. **uv** (Python environment manager) — in Terminal:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

4. **Git** — in Terminal:

   ```bash
   brew install git
   ```

> If you are unsure whether any of these are already installed, open Terminal and type the tool name followed by `--version` (e.g. `docker --version`). If you see a version number, it is installed.

---

## Setup — step by step

### Step 1: Get the code onto your machine

Open Terminal and run:

```bash
git clone https://github.com/your-username/de-template.git
cd de-template
```

> If you created a new repository from this template on GitHub, use your repository's URL instead.

---

### Step 2: Create your environment file

The `.env` file holds configuration values (database passwords, API keys) that should never be committed to Git. Create it by copying the example:

```bash
cp .env.example .env
```

Open `.env` in a text editor. The defaults will work for local development. If you have an API key for a data source, add it here.

---

### Step 3: Set up your Python environment

```bash
uv sync --group dev
```

This downloads all the Python packages the project needs and puts them in an isolated environment so they do not interfere with anything else on your machine.

---

### Step 4: Install pre-commit hooks

```bash
uv run pre-commit install
```

This sets up automatic code quality checks that run every time you make a commit. They catch common mistakes (formatting, typos, unused imports) before the code reaches GitHub.

> **Note:** The ruff hook runs with `--fix`, which means it will **automatically modify your files** to resolve lint issues before completing the commit. If this happens, re-stage the changed files (`git add -u`) and run `git commit` again.

---

### Step 5: Start the database and Airflow

Run this once the very first time. It builds the Airflow image (installs dbt and the
project's Python packages inside it) and creates the metadata tables Airflow needs
internally. The first build downloads a lot, so it can take a few minutes:

```bash
docker compose up airflow-init --build
```

Wait for it to print `Database migrating done!` and exit. Then start all services:

```bash
docker compose up -d
```

The `-d` flag runs everything in the background. Docker Desktop will show you four
running containers: `postgres`, `airflow-api-server`, `airflow-scheduler`, and
`airflow-dag-processor`.

> **Why four containers?** Airflow 3 splits responsibilities: the **api-server** serves
> the web UI and REST API, the **scheduler** decides what to run, and the
> **dag-processor** (new and required in Airflow 3) parses your DAG files. All three
> are started for you by `docker compose up`.

---

### Step 6: Verify everything is working

Open your browser and go to **<http://localhost:8080>**

You should see the Airflow login screen. Sign in with:

- Username: `admin`
- Password: `admin`

> **How login works:** Airflow 3 replaced the old `airflow users` system with the
> built-in *SimpleAuthManager*. This template ships a pre-seeded password file
> (`docker/airflow/simple_auth_manager_passwords.json`) so the login is a stable
> `admin` / `admin` instead of a random password printed in the logs. This is for
> **local development only** — do not use it as-is in a shared or production environment.

You can also connect VS Code to the database directly using the SQLTools extension —
host `localhost`, port `5432`, user `de_user`, password `de_password`, database
`warehouse`. (These values come from `.env`; the database user and the `raw` /
`staging` / `marts` schemas are created automatically by
`docker/postgres/init.sh` the first time Postgres starts.)

---

## Adding your first data source

1. **Copy the example extractor** — duplicate `extractors/api/example_api.py` and rename it for your source (e.g. `stripe_api.py`).

2. **Edit the new file** — change `BASE_URL` to your API's base URL and update the `extract` method to call the right endpoint. The method should return a list of dictionaries (one per record).

3. **Add your API key** — open `.env` and add a line like `STRIPE_API_KEY=sk_live_...`, then reference it in your extractor with `os.environ["STRIPE_API_KEY"]`.

4. **Add any new packages to `requirements-airflow.txt`** — if your extractor uses a Python package that is not already listed there (e.g. `boto3`, `stripe`), add it. This file is what gets installed inside the Docker container, so Airflow tasks will fail if a package is missing from it. Your local environment is managed separately by `pyproject.toml`.

5. **Create a DAG** — duplicate `dags/example_pipeline.py`, update it to import and call your new extractor, and set the schedule you want (e.g. `@hourly`, `@daily`).

   The `dags/`, `extractors/`, and `loaders/` folders are mounted into the containers,
   so **new and edited `.py` files are picked up automatically** within a minute — no
   restart needed.

6. **If you added a new Python package** to `requirements-airflow.txt`, the image must be
   rebuilt for Airflow to see it:

   ```bash
   docker compose up -d --build
   ```

> **About the bundled example:** `example_pipeline` points at a placeholder API
> (`api.example.com`) and reads `EXAMPLE_API_KEY` from `.env`. Its `extract_and_load`
> task is **expected to fail** if you trigger it until you swap in a real API and key —
> the DAG itself still parses and appears in the UI. Use it as a copy-paste starting
> point, then delete it once you have your own.

---

## Adding dbt models

dbt models are SQL files that live in `dbt/models/`. The folder structure follows a three-layer pattern:

| Layer | Folder | Purpose |
| --- | --- | --- |
| Staging | `dbt/models/staging/` | Rename columns, cast data types, filter bad rows |
| Intermediate | `dbt/models/intermediate/` | Join staging models together |
| Marts | `dbt/models/marts/` | Final tables — one per business question or dashboard |

Models land in exactly the schema named by their `+schema:` setting in
`dbt/dbt_project.yml` (so `marts` models go to the `marts` schema, matching the schemas
created in `init.sh`). This is handled by `dbt/macros/generate_schema_name.sql`, which
overrides dbt's default behaviour of prefixing the schema name.

To create a new model, add a `.sql` file to the appropriate folder.

dbt reads the database connection from `POSTGRES_*` environment variables (see
`dbt/profiles.yml`). The easiest way to run it is **inside the Airflow container**, where
those variables are already set:

```bash
make dbt-run-container
```

To run dbt **from your laptop** instead, load the variables from `.env` first, then call dbt
(this is what `make dbt-run` does, minus the `source` step):

```bash
set -a && source .env && set +a
uv run dbt run --project-dir dbt/ --profiles-dir dbt/
```

---

## Activating the data science layer

The notebooks and machine learning packages are installed only when you need them, keeping the default environment lean.

```bash
# Add Jupyter and pandas
uv sync --group notebooks

# Add scikit-learn, XGBoost, and MLflow
uv sync --group ml

# Launch Jupyter
uv run jupyter lab
```

Notebooks connect to the same local PostgreSQL database, so you can query your processed data directly.

---

## Stopping and starting services

```bash
# Stop all services (data is preserved)
docker compose down

# Start them again
docker compose up -d

# Stop and delete all data (fresh start)
docker compose down -v
```

---

## Project structure

```text
de-template/
│
├── dags/                        Airflow pipeline definitions
├── dbt/                         SQL transformation models
│   └── models/
│       ├── staging/             Raw → cleaned
│       ├── intermediate/        Joins and business logic
│       └── marts/               Final analytical tables
├── extractors/                  Python code that fetches data from APIs
├── loaders/                     Python code that writes data to PostgreSQL
├── docker/                      Airflow Dockerfile, Postgres init SQL, auth password file
├── docs/                        Project documentation and setup guides
├── tests/                       Automated tests
├── notebooks/                   Jupyter notebooks (activate when needed)
├── scripts/                     Helper shell scripts
├── .env.example                 Template for your local configuration
├── docker-compose.yml           Defines all Docker services
├── requirements-airflow.txt     Python packages installed inside Airflow containers
├── pyproject.toml               Python project and dependency configuration
└── Makefile                     Convenience commands (make lint, make test, make up, …)
```

---

## Running the test suite

```bash
uv run pytest
```

Tests live in `tests/`. Add tests for your extractors in `tests/test_extractors/` and for your loaders in `tests/test_loaders/`.

---

## One-command bootstrap (alternative to the steps above)

If you want to do everything in a single command:

```bash
bash scripts/init_dev.sh
```

This script runs Steps 2–5 automatically.

---

## Troubleshooting

**Docker containers won't start**
Make sure Docker Desktop is open and the whale icon is visible in the menu bar. Run `docker info` in Terminal — if you see an error, Docker is not running.

**Port 5432 or 8080 is already in use**
Another application is using that port. To find it: `lsof -i :5432` (or `:8080`). You can either stop that application or change the port mapping in `docker-compose.yml`.

**`uv` command not found**
Close Terminal, reopen it, and try again. If that does not help, run `source ~/.zshrc` (or `~/.bash_profile`) to reload your shell configuration.

**Airflow shows no DAGs**
DAG files are parsed by the `airflow-dag-processor` container. Make sure your file is
saved in the `dags/` folder and has no Python syntax errors. Check the processor's logs
for parse errors with `docker compose logs airflow-dag-processor`, or test the file
locally first with `uv run python dags/your_dag.py` (no output means it parsed cleanly).

**The web UI / login does not load (`docker compose up` shows containers restarting)**
Check which container is failing with `docker compose ps` and read its logs, e.g.
`docker compose logs airflow-api-server`. If you changed any `AIRFLOW__...` setting in
`docker-compose.yml`, a typo there is the usual cause.

**`docker compose up airflow-init` fails with "permission denied for schema public"**
This means the Postgres data volume was created before the `init.sh` fix. Reset it with
`docker compose down -v` (this deletes local data) and run Step 5 again.

# Data Engineering Template

A ready-to-use starting point for data engineering and analytics projects. Clone this repository, follow the setup steps below, and you will have a fully working local environment — with a database, a pipeline scheduler, and a data transformation layer — running on your Mac in under an hour.

---

## What is this?

This template wires together four industry-standard tools so you do not have to do it yourself:

| Tool | What it does |
| --- | --- |
| **Docker Desktop** | Runs your database and scheduler as isolated services on your laptop |
| **PostgreSQL** | The database where your raw and processed data lives |
| **Apache Airflow** | The scheduler that runs your data pipelines on a timetable |
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

Run this once the very first time — it sets up the database tables Airflow needs internally:

```bash
docker compose up airflow-init
```

Then start all services:

```bash
docker compose up -d
```

The `-d` flag runs everything in the background. Docker Desktop will show you the running containers.

---

### Step 6: Verify everything is working

Open your browser and go to **<http://localhost:8080>**

You should see the Airflow login screen. Sign in with:

- Username: `admin`
- Password: `admin`

You can also connect VS Code to the database directly using the SQLTools extension — host `localhost`, port `5432`, user `de_user`, password `de_password`, database `warehouse`.

---

## Adding your first data source

1. **Copy the example extractor** — duplicate `extractors/api/example_api.py` and rename it for your source (e.g. `stripe_api.py`).

2. **Edit the new file** — change `BASE_URL` to your API's base URL and update the `extract` method to call the right endpoint. The method should return a list of dictionaries (one per record).

3. **Add your API key** — open `.env` and add a line like `STRIPE_API_KEY=sk_live_...`, then reference it in your extractor with `os.environ["STRIPE_API_KEY"]`.

4. **Add any new packages to `requirements-airflow.txt`** — if your extractor uses a Python package that is not already listed there (e.g. `boto3`, `stripe`), add it. This file is what gets installed inside the Docker container, so Airflow tasks will fail if a package is missing from it. Your local environment is managed separately by `pyproject.toml`.

5. **Create a DAG** — duplicate `dags/example_pipeline.py`, update it to import and call your new extractor, and set the schedule you want (e.g. `@hourly`, `@daily`).

6. **Restart Airflow** so it picks up the new DAG:

   ```bash
   docker compose restart airflow-scheduler airflow-webserver
   ```

---

## Adding dbt models

dbt models are SQL files that live in `dbt/models/`. The folder structure follows a three-layer pattern:

| Layer | Folder | Purpose |
| --- | --- | --- |
| Staging | `dbt/models/staging/` | Rename columns, cast data types, filter bad rows |
| Intermediate | `dbt/models/intermediate/` | Join staging models together |
| Marts | `dbt/models/marts/` | Final tables — one per business question or dashboard |

To create a new model, add a `.sql` file to the appropriate folder. Then run:

```bash
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
├── docker/                      Dockerfile and database initialisation SQL
├── docs/                        Project documentation and setup guides
├── tests/                       Automated tests
├── notebooks/                   Jupyter notebooks (activate when needed)
├── scripts/                     Helper shell scripts
├── .env.example                 Template for your local configuration
├── docker-compose.yml           Defines all Docker services
├── requirements-airflow.txt     Python packages installed inside Airflow containers
└── pyproject.toml               Python project and dependency configuration
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
Make sure your DAG file is saved in the `dags/` folder and has no Python syntax errors. Run `python dags/your_dag.py` to check for errors before restarting the scheduler.

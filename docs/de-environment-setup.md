# Data Engineering Template: Development Environment Setup Guide

> **Stack:** macOS · Docker Compose · PostgreSQL · Apache Airflow · dbt Core · uv · VS Code

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Repository Structure](#3-repository-structure)
4. [Docker & Docker Compose Setup](#4-docker--docker-compose-setup)
5. [Python Environment with uv](#5-python-environment-with-uv)
6. [VS Code Setup](#6-vs-code-setup)
7. [Step-by-Step Bootstrapping Guide](#7-step-by-step-bootstrapping-guide)
8. [Key Files Reference](#8-key-files-reference)
9. [Development Workflow](#9-development-workflow)
10. [Modular DS Layer (Future)](#10-modular-ds-layer-future)

---

## 1. Architecture Overview

```text
REST APIs
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  EXTRACT & LOAD  (Python + Airflow DAGs)             │
│  extractors/ — fetch data from APIs                  │
│  loaders/    — write raw data to PostgreSQL          │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  TRANSFORM  (dbt Core)                               │
│  raw → staging → intermediate → marts               │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  SERVING  (PostgreSQL marts schema)                  │
│  Ready for analysis, dashboards, or ML (future)      │
└─────────────────────────────────────────────────────┘

Docker Compose Services:
  ┌──────────┐  ┌────────────────────┐  ┌──────────────────┐
  │ postgres │  │ airflow-webserver   │  │ airflow-scheduler│
  └──────────┘  └────────────────────┘  └──────────────────┘
                ┌──────────────────────┐
                │ airflow-init (once)  │
                └──────────────────────┘
```

**Why this separation matters (SE/MLE mindset):**

- Each concern (extract, load, transform, serve) is independently testable and deployable
- Docker Compose means the entire stack starts with one command on any machine
- uv dependency groups mean a collaborator only installs what they need

---

## 2. Prerequisites

Install these on your Mac before anything else.

### 2.1 Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2.2 Docker Desktop for Mac

```bash
brew install --cask docker
```

After install, open Docker Desktop from Applications and let it finish its first-run setup.
Allocate at least **4 CPUs** and **6 GB RAM** in Docker Desktop → Settings → Resources (Airflow is memory-hungry).

### 2.3 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify: `uv --version`

### 2.4 Git

```bash
brew install git
```

### 2.5 GitHub CLI (optional but recommended)

```bash
brew install gh
gh auth login
```

---

## 3. Repository Structure

```text
de-template/
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # Lint + type check + test on push (GitHub Actions)
│
├── dags/
│   └── example_pipeline.py         # Starter DAG: extract → load → dbt run
│
├── dbt/
│   ├── models/
│   │   ├── staging/                # 1:1 with raw tables, light cleaning
│   │   ├── intermediate/           # Business logic joins
│   │   └── marts/                  # Final consumption-ready tables
│   ├── tests/                      # dbt singular tests (custom SQL assertions)
│   ├── macros/                     # Reusable Jinja macros
│   ├── seeds/                      # Small static CSV reference data
│   ├── dbt_project.yml
│   └── profiles.yml                # Points to Dockerised PostgreSQL
│
├── extractors/
│   ├── __init__.py
│   ├── base.py                     # Abstract base class — all extractors inherit this
│   └── api/
│       └── example_api.py          # Concrete REST API extractor (copy to add a source)
│
├── loaders/
│   ├── __init__.py
│   └── postgres_loader.py          # Writes raw records to PostgreSQL
│
├── tests/
│   ├── conftest.py
│   ├── test_extractors/
│   │   ├── test_base.py
│   │   └── test_example_api.py
│   └── test_loaders/
│       └── test_postgres_loader.py
│
├── notebooks/                      # Placeholder — kept empty, activated later
│   └── .gitkeep
│
├── docker/
│   ├── airflow/
│   │   └── Dockerfile              # Extends official Airflow image; installs requirements-airflow.txt
│   └── postgres/
│       └── init.sql                # Creates databases, users, and schemas on first run
│
├── scripts/
│   └── init_dev.sh                 # One-command local bootstrap (Steps 2–5)
│
├── docs/
│   └── de-environment-setup.md     # This file
│
├── .env.example                    # Template — NEVER commit .env itself
├── .gitignore
├── docker-compose.yml
├── pyproject.toml                  # uv-managed; defines all dependency groups
├── requirements-airflow.txt        # Runtime deps installed inside the Airflow Docker image
└── uv.lock                         # Locked dependency graph (commit this)
```

### Why this structure follows SE conventions

- **`extractors/base.py`** — an abstract base class enforces a contract on all future extractors. You're not writing one-off scripts; you're building a pattern.
- **`tests/test_extractors/` vs `tests/test_loaders/`** — mirrors production engineering test strategy. Tests are colocated with the layer they cover.
- **`requirements-airflow.txt`** — decouples what runs inside Docker from the local developer environment managed by `pyproject.toml`. Add packages here if your Airflow DAG needs them at runtime.
- **`.env.example`** — documents required environment variables without committing secrets.

---

## 4. Docker & Docker Compose Setup

### 4.1 What Docker Compose does (beginner explainer)

Think of `docker-compose.yml` as a recipe that says:
> "Start these N services (postgres, airflow, etc.), wire them together on a shared network, and mount these folders from my Mac into the containers."

You'll primarily use:

```bash
docker compose up airflow-init          # One-time Airflow DB setup
docker compose up -d                    # Start all services in background
docker compose down                     # Stop all services
docker compose logs -f                  # Tail container logs
```

### 4.2 `docker-compose.yml`

```yaml
version: "3.9"

x-airflow-common: &airflow-common
  build:
    context: ./docker/airflow
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow_db
    AIRFLOW__CORE__FERNET_KEY: ""
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    AIRFLOW__WEBSERVER__EXPOSE_CONFIG: "true"
    _PIP_ADDITIONAL_REQUIREMENTS: ""
  volumes:
    - ./dags:/opt/airflow/dags
    - ./extractors:/opt/airflow/extractors
    - ./loaders:/opt/airflow/loaders
    - ./dbt:/opt/airflow/dbt
    - airflow_logs:/opt/airflow/logs
  depends_on:
    postgres:
      condition: service_healthy
  env_file:
    - .env

services:

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 10s
      retries: 5
      start_period: 5s

  airflow-init:
    <<: *airflow-common
    command: >
      bash -c "airflow db migrate &&
               airflow users create
                 --username admin
                 --password admin
                 --firstname Admin
                 --lastname User
                 --role Admin
                 --email admin@example.com"
    restart: "no"

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"
    restart: unless-stopped

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    restart: unless-stopped

volumes:
  postgres_data:
  airflow_logs:
```

**Key design notes:**

- The postgres superuser is `postgres` (not `de_user`). `init.sql` creates the application users separately.
- Airflow uses its own dedicated database (`airflow_db`) and user (`airflow`). Your pipeline data lives in the `warehouse` database under the `de_user` account.
- DAGs, extractors, loaders, and dbt are mounted directly from your local checkout — no rebuild needed when you change Python or SQL files.

### 4.3 `docker/airflow/Dockerfile`

```dockerfile
FROM apache/airflow:3.1.8-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean

USER airflow

# Install dbt and project runtime dependencies
COPY --chown=airflow:root requirements-airflow.txt /opt/airflow/
RUN pip install --no-cache-dir -r /opt/airflow/requirements-airflow.txt
```

> If you add a Python package that your DAGs or extractors need at runtime, add it to `requirements-airflow.txt` and rebuild with `docker compose build`.

### 4.4 `docker/postgres/init.sql`

```sql
-- Create separate databases
CREATE DATABASE airflow_db;
CREATE DATABASE warehouse;

-- Airflow's dedicated Postgres user
CREATE USER airflow WITH PASSWORD 'airflow';
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow;

-- Connect to warehouse and create ELT schemas
\c warehouse;
CREATE SCHEMA IF NOT EXISTS raw;        -- Landing zone for API data
CREATE SCHEMA IF NOT EXISTS staging;    -- dbt staging models
CREATE SCHEMA IF NOT EXISTS marts;      -- dbt final models

-- Application user for pipeline code
CREATE USER de_user WITH PASSWORD 'de_password';
GRANT ALL PRIVILEGES ON DATABASE warehouse TO de_user;
GRANT ALL PRIVILEGES ON SCHEMA raw, staging, marts TO de_user;
```

This runs automatically the first time the `postgres` container starts. It will **not** re-run on subsequent starts — delete the `postgres_data` Docker volume (`docker compose down -v`) if you need a fresh database.

---

## 5. Python Environment with uv

### 5.1 `pyproject.toml`

This is the single source of truth for all Python dependencies. uv's dependency groups let you install only what each context needs.

```toml
[project]
name = "de-template"
version = "0.1.0"
description = "General-purpose data engineering & data science project template"
requires-python = ">=3.12"

# Core runtime dependencies — always installed
dependencies = [
    "apache-airflow>=3.1.0",
    "dbt-postgres>=1.8.0",
    "psycopg2-binary>=2.9.9",
    "sqlalchemy>=2.0.0",
    "requests>=2.31.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "pydantic>=2.7.0",
    "tenacity>=8.3.0",
    "structlog>=24.0.0",
]

[dependency-groups]

# Install for local development
dev = [
    "pytest>=8.2.0",
    "pytest-cov>=5.0.0",
    "pytest-httpx>=0.30.0",  # Mock httpx calls in tests — no real HTTP needed
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "pre-commit>=3.7.0",
    "types-requests>=2.31.0",
]

# Activate later: `uv sync --group notebooks`
notebooks = [
    "jupyter>=1.0.0",
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "matplotlib>=3.9.0",
    "seaborn>=0.13.0",
    "sqlalchemy>=2.0.0",
]

# Activate for ML experimentation: `uv sync --group ml`
ml = [
    "scikit-learn>=1.5.0",
    "xgboost>=2.0.0",
    "mlflow>=2.13.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# Required because project name (de-template) differs from package directories
[tool.hatch.build.targets.wheel]
packages = ["extractors", "loaders"]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]  # Error, Pyflakes, isort, pyupgrade, bugbear

[tool.mypy]
python_version = "3.12"
strict = false
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=extractors --cov=loaders --cov-report=term-missing"
```

### 5.2 Local environment setup commands

```bash
# Install all dev dependencies (creates .venv automatically)
uv sync --group dev

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy extractors/ loaders/
```

> There is no need to manually create or activate a virtual environment. `uv sync` creates `.venv/` and `uv run` uses it automatically.

### 5.3 Why each dependency was chosen

| Package | Purpose | SE/MLE Lesson |
| --- | --- | --- |
| `pydantic` | Validates API response shapes | Forces you to define data contracts, not just `dict` access |
| `tenacity` | Retries failed API calls with backoff | Real APIs fail. Production code handles this gracefully |
| `structlog` | JSON-structured logging | Logs become queryable in production observability tools |
| `httpx` | HTTP client (sync + async ready) | Used by extractors and mockable in tests via `pytest-httpx` |
| `sqlalchemy` | Database abstraction for the loader | Engine/connection management; works with any SQL database |
| `ruff` | Linting + formatting | One tool replaces flake8/black/isort; enforces style automatically |
| `mypy` | Static type checking | Catches bugs before runtime; encourages type annotations |
| `pre-commit` | Auto-runs ruff + mypy on `git commit` | Code quality is automated, not manual |

---

## 6. VS Code Setup

### 6.1 Recommended extensions (`.vscode/extensions.json`)

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "ms-azuretools.vscode-docker",
    "mtxr.sqltools",
    "mtxr.sqltools-driver-pg",
    "innoverio.vscode-dbt-power-user",
    "GitHub.copilot",
    "anthropics.claude-code"
  ]
}
```

### 6.2 Workspace settings (`.vscode/settings.json`)

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "sqltools.connections": [
    {
      "name": "Local Postgres — warehouse (Docker)",
      "driver": "PostgreSQL",
      "server": "localhost",
      "port": 5432,
      "database": "warehouse",
      "username": "de_user"
    }
  ]
}
```

### 6.3 Using Claude Code effectively

Once Claude Code is installed in VS Code, you'll use it most effectively for:

- **Generating extractor subclasses** — describe the API, ask it to implement the `BaseExtractor` interface
- **Writing dbt models** — paste your raw schema, ask for a staging model with standard conventions
- **Writing tests** — ask it to generate `pytest` test cases for a given function
- **Debugging Docker issues** — paste error logs and ask for diagnosis

---

## 7. Step-by-Step Bootstrapping Guide

Follow these steps exactly once to go from zero to a running stack.

```bash
# Step 1: Clone the repo
git clone https://github.com/YOUR_USERNAME/de-template.git
cd de-template

# Step 2: Configure environment variables
cp .env.example .env
# Edit .env if you want to override the defaults (defaults work for local dev)

# Step 3: Install Python dev dependencies
uv sync --group dev

# Step 4: Install pre-commit hooks
uv run pre-commit install

# Step 5: Initialise Airflow (one time only)
# Sets up Airflow's internal DB tables and creates the admin user
docker compose up airflow-init

# Step 6: Start all services
docker compose up -d

# Step 7: Verify everything is running
# Open: http://localhost:8080  → Airflow UI (admin / admin)
# Connect SQLTools → localhost:5432, database: warehouse, user: de_user, password: de_password
```

> You can also run Steps 2–5 in a single command: `bash scripts/init_dev.sh`

### `.env.example`

```bash
# PostgreSQL — used by extractors/loaders running locally or inside Airflow
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=de_user
POSTGRES_PASSWORD=de_password
POSTGRES_DB=warehouse

# Airflow container UID (prevents permission issues on mounted volumes)
AIRFLOW_UID=50000

# API Keys — add your sources below
# EXAMPLE_API_KEY=your_key_here
```

> **Docker networking note:** Inside containers, services talk to each other using the service name as the hostname (e.g. `postgres`), not `localhost`. The Airflow connection string in `docker-compose.yml` already uses `postgres` as the host. Your local SQLTools/psycopg2 connects to `localhost:5432`. This trips up almost everyone the first time.

---

## 8. Key Files Reference

### `extractors/base.py`

```python
from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """Abstract base class for all data extractors.

    Subclass this and implement `extract` to pull data from any source.
    The returned records are plain dicts ready for the loader layer.
    """

    @abstractmethod
    def extract(self) -> list[dict[str, Any]]:
        """Pull data from the source and return a list of records."""
        ...
```

Every extractor must implement `extract()` and return `list[dict]`. The loader accepts whatever this returns.

### `extractors/api/example_api.py` (starter pattern)

```python
class ExampleApiExtractor(BaseExtractor):
    BASE_URL = "https://api.example.com/v1"

    def __init__(self) -> None:
        self.api_key = os.environ["EXAMPLE_API_KEY"]   # Raises KeyError if missing
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _get(self, path: str, params=None) -> list[dict]:
        response = self.client.get(f"{self.BASE_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()

    def extract(self) -> list[dict]:
        return self._get("/items")
```

Copy this file, rename it, and change `BASE_URL` plus the `extract()` body for each new API source.

### `loaders/postgres_loader.py`

The loader auto-creates the target schema and table on first run, then inserts records using SQLAlchemy named-parameter `executemany`. The `table` argument can be `"raw.users"` or just `"users"` (defaults to `raw` schema).

### `requirements-airflow.txt`

Contains runtime dependencies installed inside the Airflow Docker image. Separate from `pyproject.toml` which manages your local environment.

```text
dbt-postgres>=1.8.0
psycopg2-binary>=2.9.9
sqlalchemy>=2.0.0
requests>=2.31.0
httpx>=0.27.0
python-dotenv>=1.0.0
pydantic>=2.7.0
tenacity>=8.3.0
structlog>=24.0.0
```

Add new packages here and run `docker compose build` if a DAG task needs them at runtime.

### `.github/workflows/ci.yml`

Runs on every push to `main`/`develop` and on PRs to `main`:

1. Install uv
2. `uv sync --group dev`
3. `uv run ruff check .`
4. `uv run mypy extractors/ loaders/`
5. `uv run pytest`

---

## 9. Development Workflow

Once the stack is running, your day-to-day loop looks like:

```text
1. Copy extractors/api/example_api.py → extractors/api/my_source.py
      ↓ change BASE_URL, implement extract()
2. Add API key to .env (e.g. MY_SOURCE_API_KEY=...)
3. Write unit tests → tests/test_extractors/test_my_source.py
      ↓ uv run pytest
4. Wire it into an Airflow DAG → dags/my_pipeline.py
      ↓ visible in http://localhost:8080
5. DAG writes raw data → PostgreSQL raw schema
      ↓ inspect with VS Code SQLTools (database: warehouse)
6. Write dbt staging model → dbt/models/staging/stg_my_source.sql
      ↓ uv run dbt run --project-dir dbt/ --profiles-dir dbt/
7. Promote to intermediate + mart models
8. Commit → pre-commit hooks auto-lint → push → GitHub Actions CI runs
```

---

## 10. Modular DS Layer (Future)

When you're ready to add the data science layer, the changes are isolated:

```bash
# Install the notebooks group — nothing else changes
uv sync --group notebooks

# Or install the ML group
uv sync --group ml

# Launch Jupyter
uv run jupyter lab
```

Then optionally add to `docker-compose.yml`:

```yaml
  jupyter:
    image: jupyter/scipy-notebook:latest
    ports:
      - "8888:8888"
    volumes:
      - ./notebooks:/home/jovyan/work
    environment:
      - JUPYTER_ENABLE_LAB=yes
```

Your `notebooks/` folder is already in the repo, kept empty until activated. The data engineering layer is completely unchanged.

---

## Quick Reference Card

| Goal | Command |
| --- | --- |
| Install dev dependencies | `uv sync --group dev` |
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy extractors/ loaders/` |
| Start entire stack | `docker compose up -d` |
| Stop entire stack | `docker compose down` |
| Tail all logs | `docker compose logs -f` |
| Rebuild Airflow image | `docker compose build` |
| Run dbt models locally | `uv run dbt run --project-dir dbt/ --profiles-dir dbt/` |
| Run dbt inside container | `docker compose exec airflow-scheduler bash -c "cd /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt"` |
| Airflow UI | `http://localhost:8080` (admin / admin) |
| Connect to Postgres | localhost:5432, database: warehouse, user: de_user |
| Fresh database (delete all data) | `docker compose down -v` |

# Data Engineering Template: Development Environment Setup Guide

## Overview

This guide walks you through setting up a **reproducible, production-minded development environment** on macOS for a data engineering project using:

- **Docker Desktop** — containerised services (PostgreSQL, Airflow)
- **uv** — fast Python package and environment management
- **dbt Core** — data transformation layer
- **Apache Airflow** — orchestration
- **VS Code + Claude Code** — development IDE

The philosophy here is **modular by default**: the data science layer (Jupyter, pandas, etc.) is defined but dormant until you need it.

---

## Step 1: Install Core Local Tools

These are installed directly on your Mac — not inside Docker.

### 1.1 Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1.2 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:
```bash
uv --version
```

### 1.3 Docker Desktop for Mac

Download from: https://www.docker.com/products/docker-desktop/

After installing, open Docker Desktop and ensure it is running (whale icon in menu bar).

Verify:
```bash
docker --version
docker compose version
```

> **Beginner tip:** Docker Desktop gives you a GUI to see running containers, logs, and resource usage — use it heavily early on.

### 1.4 Git

```bash
brew install git
```

### 1.5 VS Code Extensions

Install these from the VS Code Extensions panel (`Cmd+Shift+X`):

| Extension | Purpose |
|---|---|
| `ms-python.python` | Python language support |
| `ms-python.pylance` | Type checking & IntelliSense |
| `charliermarsh.ruff` | Fast linting & formatting |
| `ms-azuretools.vscode-docker` | Docker file support & container management |
| `innoverio.vscode-dbt-power-user` | dbt model previews & lineage |
| `mtxr.sqltools` | Query PostgreSQL directly from VS Code |
| `mtxr.sqltools-driver-pg` | PostgreSQL driver for SQLTools |
| `tamasfe.even-better-toml` | `pyproject.toml` syntax highlighting |
| `eamodio.gitlens` | Enhanced Git history & blame |
| `claude-code` | Claude Code AI assistant |

---

## Step 2: GitHub Template Repository Structure

### 2.1 Recommended Directory Layout

```
de-template/
│
├── .github/
│   ├── workflows/
│   │   └── ci.yml              # Lint + test on push/PR
│   └── PULL_REQUEST_TEMPLATE.md
│
├── dags/                        # Airflow DAG definitions
│   └── example_pipeline.py
│
├── dbt/                         # dbt Core project
│   ├── models/
│   │   ├── staging/             # Raw → typed, renamed
│   │   ├── intermediate/        # Business logic joins
│   │   └── marts/               # Final analytical tables
│   ├── tests/
│   ├── macros/
│   ├── seeds/
│   ├── dbt_project.yml
│   └── profiles.yml             # Points to Postgres (uses env vars)
│
├── extractors/                  # Python extraction modules (EL layer)
│   ├── __init__.py
│   ├── base.py                  # Abstract base class for all extractors
│   └── api/
│       ├── __init__.py
│       └── example_api.py       # Concrete REST API extractor
│
├── loaders/                     # Load raw data into Postgres raw schema
│   ├── __init__.py
│   └── postgres_loader.py
│
├── docker/
│   ├── airflow/
│   │   └── Dockerfile           # Extends official Airflow image
│   └── postgres/
│       └── init.sql             # Creates raw/staging/marts schemas
│
├── tests/                       # pytest unit + integration tests
│   ├── conftest.py
│   ├── test_extractors/
│   └── test_loaders/
│
├── notebooks/                   # DS layer — dormant, activate via uv group
│   └── .gitkeep
│
├── scripts/
│   └── init_dev.sh              # One-command local environment bootstrap
│
├── .env.example                 # Committed env var template (no secrets)
├── .gitignore
├── .pre-commit-config.yaml      # Ruff + mypy hooks
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

### 2.2 Why This Structure?

- **`extractors/`** separates the EL concern from orchestration (DAGs just call extractor classes)
- **`dbt/` models in 3 layers** mirrors the Medallion/ELT pattern: raw → staging → marts
- **`notebooks/`** is present but empty — scaffolded for when the DS layer is activated
- **`docker/`** keeps Dockerfiles co-located but separate from application code

---

## Step 3: pyproject.toml with uv Dependency Groups

```toml
[project]
name = "de-template"
version = "0.1.0"
description = "General-purpose data engineering & data science project template"
requires-python = ">=3.11"

# ── Core runtime dependencies ──────────────────────────────────────────────
dependencies = [
    "apache-airflow>=2.9.0",
    "dbt-postgres>=1.8.0",
    "psycopg2-binary>=2.9.9",
    "sqlalchemy>=2.0.0",
    "requests>=2.31.0",
    "httpx>=0.27.0",          # Modern async-capable HTTP client for REST APIs
    "python-dotenv>=1.0.0",
    "pydantic>=2.7.0",        # Data validation (great for API response models)
    "tenacity>=8.3.0",        # Retry logic for API calls
    "structlog>=24.0.0",      # Structured JSON logging
]

# ── Optional dependency groups ─────────────────────────────────────────────
[dependency-groups]

dev = [
    "pytest>=8.2.0",
    "pytest-cov>=5.0.0",
    "pytest-httpx>=0.30.0",   # Mock HTTP calls in tests
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
    "sqlalchemy>=2.0.0",      # Re-listed for notebook DB access
]

# Activate for ML experimentation later
ml = [
    "scikit-learn>=1.5.0",
    "xgboost>=2.0.0",
    "mlflow>=2.13.0",
]


[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# ── Tool configuration ─────────────────────────────────────────────────────
[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]   # pycodestyle, pyflakes, isort, pyupgrade, bugbear

[tool.mypy]
python_version = "3.11"
strict = false
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=extractors --cov=loaders --cov-report=term-missing"
```

### Key uv Commands

```bash
# Create a virtual environment and install all core deps
uv sync

# Install core + dev dependencies (for local development)
uv sync --group dev

# Activate the DS layer when ready
uv sync --group notebooks

# Add a new package
uv add httpx

# Add a dev-only package
uv add --group dev pytest-httpx

# Run a command inside the managed environment
uv run pytest
uv run ruff check .
```

---

## Step 4: Docker Compose — Services Architecture

### Service Design Decisions

For a beginner-friendly setup, we use **Airflow with LocalExecutor**, which runs tasks in the same process rather than distributing them — this removes the need for Redis/Celery and keeps the service count low.

Both Airflow and your data warehouse share **one PostgreSQL instance** on separate databases:
- `airflow_db` — Airflow metadata
- `warehouse` — your actual data (schemas: `raw`, `staging`, `marts`)

```
┌─────────────────────────────────────────────┐
│              docker-compose.yml              │
│                                              │
│  ┌──────────────┐    ┌─────────────────────┐ │
│  │  postgres    │    │  airflow-webserver  │ │
│  │  port: 5432  │◄───│  port: 8080         │ │
│  │              │    └─────────────────────┘ │
│  │  DB: airflow │    ┌─────────────────────┐ │
│  │  DB: warehouse◄───│  airflow-scheduler  │ │
│  └──────────────┘    └─────────────────────┘ │
│                                              │
└─────────────────────────────────────────────┘
       ▲ localhost:5432 accessible from VS Code (SQLTools)
```

### docker-compose.yml

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
    # Pass your .env vars into Airflow containers
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

### docker/postgres/init.sql

```sql
-- Create separate databases
CREATE DATABASE airflow_db;
CREATE DATABASE warehouse;

-- Connect to warehouse and create ELT schemas
\c warehouse;
CREATE SCHEMA IF NOT EXISTS raw;        -- Landing zone for API data
CREATE SCHEMA IF NOT EXISTS staging;    -- dbt staging models
CREATE SCHEMA IF NOT EXISTS marts;      -- dbt final models

-- Create a dedicated app user
CREATE USER de_user WITH PASSWORD 'de_password';
GRANT ALL PRIVILEGES ON DATABASE warehouse TO de_user;
GRANT ALL PRIVILEGES ON SCHEMA raw, staging, marts TO de_user;
```

### docker/airflow/Dockerfile

```dockerfile
FROM apache/airflow:2.9.2-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean

USER airflow

# Install dbt and project dependencies inside Airflow image
COPY --chown=airflow:root requirements-airflow.txt /opt/airflow/
RUN pip install --no-cache-dir -r /opt/airflow/requirements-airflow.txt
```

> **Note:** Airflow uses pip internally, so we maintain a separate `requirements-airflow.txt` for the Airflow image, while `pyproject.toml` manages your local uv environment. This is a common real-world pattern.

---

## Step 5: Key Configuration Files

### .env.example

```bash
# ── Postgres ───────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=de_user
POSTGRES_PASSWORD=de_password
POSTGRES_DB=warehouse

# ── Airflow ────────────────────────────────────
AIRFLOW_UID=50000

# ── API Keys (add your sources here) ───────────
# EXAMPLE_API_KEY=your_key_here
```

Copy this to `.env` and fill in real values. **Never commit `.env`.**

### .gitignore (key entries)

```
# Environment
.env
.venv/
__pycache__/
*.pyc

# uv
.python-version

# dbt
dbt/target/
dbt/logs/
dbt/.user.yml

# Airflow
airflow/logs/

# Notebooks
.ipynb_checkpoints/
notebooks/**/*.ipynb   # Optional: exclude notebooks from git

# OS
.DS_Store
```

### dbt/profiles.yml

```yaml
de_template:
  target: dev
  outputs:
    dev:
      type: postgres
      host: "{{ env_var('POSTGRES_HOST', 'localhost') }}"
      port: "{{ env_var('POSTGRES_PORT', '5432') | int }}"
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: staging
      threads: 4
```

---

## Step 6: GitHub Actions CI Pipeline

### .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync --group dev

      - name: Lint with Ruff
        run: uv run ruff check .

      - name: Type check with mypy
        run: uv run mypy extractors/ loaders/

      - name: Run tests
        run: uv run pytest
```

---

## Step 7: Bootstrapping a New Project from This Template

Once you've pushed this as a GitHub Template Repository:

```bash
# 1. Use as template on GitHub UI → "Use this template"

# 2. Clone your new repo
git clone https://github.com/your-username/your-project.git
cd your-project

# 3. Copy and fill in environment variables
cp .env.example .env
# edit .env with your values

# 4. Install Python environment locally
uv sync --group dev

# 5. Set up pre-commit hooks
uv run pre-commit install

# 6. Start Docker services (first time — builds images)
docker compose up airflow-init   # One-time DB setup
docker compose up -d             # Start all services

# 7. Verify
open http://localhost:8080       # Airflow UI (admin/admin)
# Connect VS Code SQLTools to localhost:5432
```

---

## Step 8: Activating the Data Science Layer (When Ready)

When you're ready to add notebooks and ML:

```bash
# Install the notebooks group
uv sync --group notebooks --group ml

# Launch Jupyter (runs in your uv environment)
uv run jupyter lab
```

No Docker changes needed — notebooks run locally against the Dockerised PostgreSQL on `localhost:5432`.

---

## Architecture Summary

```
Your Mac (local)
├── uv venv          ← Python deps, ruff, mypy, pytest, dbt CLI
├── VS Code          ← Development IDE + Claude Code
└── Docker Desktop
    ├── postgres:16  ← Metadata DB (Airflow) + Warehouse (raw/staging/marts)
    ├── airflow-webserver  :8080
    └── airflow-scheduler

Data Flow:
REST API → extractors/ → loaders/ → Postgres (raw schema)
                                         ↓
                              dbt Core (staging → marts)
                                         ↓
                              Airflow DAG orchestrates all steps
```

---

## Recommended Learning Path

1. **Week 1:** Get Docker services running, connect SQLTools to Postgres, browse Airflow UI
2. **Week 2:** Write your first extractor class (extend `base.py`), load data into `raw` schema manually
3. **Week 3:** Write dbt staging models on top of raw data, run `dbt run` locally
4. **Week 4:** Write an Airflow DAG that calls your extractor → loader → `dbt run`
5. **Later:** Activate `notebooks` group for EDA; add `ml` group for experimentation

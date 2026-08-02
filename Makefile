# Convenience entry points for the common tasks. `make` on its own lists them.
#
# The Python project is rooted here and managed by uv; the runtime services
# (Postgres + Airflow 3) run under docker compose.

PYTHON_VERSION ?= 3.12
AIRFLOW_PORT ?= 8080
POSTGRES_PORT ?= 5432
DBT_DIR := dbt
COMPOSE := docker compose

# Local dbt and export targets need WAREHOUSE_*/POSTGRES_* in the environment.
# `.env` is the single source for them; load it if it exists.
LOAD_ENV = set -a; [ -f .env ] && . ./.env || true; set +a;

.DEFAULT_GOAL := help
.PHONY: help setup install hooks lint format typecheck test test-integration check \
        up down logs build airflow-init reset \
        dbt-run dbt-test dbt-run-container export demo-handoff clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

## ── Setup ────────────────────────────────────────────────────────────────────

setup: ## One-command bootstrap: env file, Python deps, hooks, Docker services
	PYTHON_VERSION=$(PYTHON_VERSION) ./scripts/init_dev.sh

install: ## Install the Python environment and git hooks only (no Docker)
	uv sync --group dev
	uv run pre-commit install

hooks: ## (Re)install the git pre-commit hook
	uv run pre-commit install

## ── Checks ───────────────────────────────────────────────────────────────────

lint: ## Run every pre-commit hook across the repository
	uv run pre-commit run --all-files

format: ## Format the codebase with Ruff
	uv run ruff format .

typecheck: ## Type-check with mypy
	uv run mypy core/ extractors/ loaders/ exporters/ dags/

test: ## Run the test suite
	uv run pytest

test-integration: ## Run the Postgres type-fidelity tests in a throwaway container
	./scripts/with_test_postgres.sh uv run pytest tests/test_exporters/test_postgres_types.py -v --no-cov

check: lint test ## Everything CI runs

## ── Docker ───────────────────────────────────────────────────────────────────

up: ## Start Postgres and Airflow in the background
	@echo "Airflow UI  →  http://localhost:$(AIRFLOW_PORT)  (admin / admin)"
	$(COMPOSE) up -d

down: ## Stop all services (data is preserved)
	$(COMPOSE) down

logs: ## Follow the logs of all services
	$(COMPOSE) logs -f

build: ## Rebuild the Airflow image (after changing requirements-airflow.txt)
	$(COMPOSE) build

airflow-init: ## First-time Airflow metadata database setup (safe to re-run)
	$(COMPOSE) up airflow-init --build

reset: ## Stop everything and DELETE all local data, then start fresh
	$(COMPOSE) down -v
	$(COMPOSE) up airflow-init --build
	$(COMPOSE) up -d

## ── dbt ──────────────────────────────────────────────────────────────────────

dbt-run: ## Run dbt models from your laptop
	$(LOAD_ENV) uv run dbt run --project-dir $(DBT_DIR)/ --profiles-dir $(DBT_DIR)/

dbt-test: ## Run dbt tests from your laptop
	$(LOAD_ENV) uv run dbt test --project-dir $(DBT_DIR)/ --profiles-dir $(DBT_DIR)/

dbt-run-container: ## Run dbt models inside the Airflow container
	$(COMPOSE) exec airflow-scheduler bash -c \
		"cd /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt"

## ── Hand-off to ds-template-local ────────────────────────────────────────────

export: ## Export the configured marts to files for the DS project
	$(LOAD_ENV) uv run python -m exporters.cli

demo-handoff: ## Build demo marts, export them, and verify the DS project can read them
	./scripts/with_test_postgres.sh uv run python -m scripts.demo_handoff

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf $(DBT_DIR)/target $(DBT_DIR)/logs $(DBT_DIR)/dbt_packages
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

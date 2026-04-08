.PHONY: install lint format typecheck test check up down logs build dbt-run dbt-test

## ── Local dev ────────────────────────────────────────────────────────────────

install:
	uv sync --group dev
	uv run pre-commit install

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy extractors/ loaders/ dags/

test:
	uv run pytest

# Run all checks (mirrors CI)
check: lint
	uv run ruff format --check .
	uv run mypy extractors/ loaders/ dags/
	uv run pytest

## ── Docker ───────────────────────────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

# First-time Airflow setup (run once)
airflow-init:
	docker compose up airflow-init

## ── dbt ──────────────────────────────────────────────────────────────────────

dbt-run:
	uv run dbt run --project-dir dbt/ --profiles-dir dbt/

dbt-test:
	uv run dbt test --project-dir dbt/ --profiles-dir dbt/

dbt-run-container:
	docker compose exec airflow-scheduler bash -c "cd /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt"

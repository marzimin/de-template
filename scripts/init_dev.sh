#!/usr/bin/env bash
set -euo pipefail

echo "==> Copying .env.example to .env (if not present)"
[ -f .env ] || cp .env.example .env

echo "==> Installing Python environment (core + dev)"
uv sync --group dev

echo "==> Installing pre-commit hooks"
uv run pre-commit install

echo "==> Building image and initialising the Airflow metadata database"
docker compose up airflow-init --build

echo "==> Starting Docker services"
docker compose up -d

echo ""
echo "Done! Services running:"
echo "  Airflow UI  →  http://localhost:8080  (admin / admin)"
echo "  Postgres    →  localhost:5432"

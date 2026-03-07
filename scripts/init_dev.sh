#!/usr/bin/env bash
set -euo pipefail

echo "==> Copying .env.example to .env (if not present)"
[ -f .env ] || cp .env.example .env

echo "==> Installing Python environment (core + dev)"
uv sync --group dev

echo "==> Installing pre-commit hooks"
uv run pre-commit install

echo "==> Starting Docker services (first run builds images)"
docker compose up airflow-init
docker compose up -d

echo ""
echo "Done! Services running:"
echo "  Airflow UI  →  http://localhost:8080  (admin / admin)"
echo "  Postgres    →  localhost:5432"

#!/usr/bin/env bash
set -euo pipefail

# One-command bootstrap. Invoked by `make setup`.
# Always operates on the repository root, regardless of where it is called from.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

echo "==> Copying .env.example to .env (if not present)"
[ -f .env ] || cp .env.example .env

echo "==> Installing Python environment (core + dev) using Python ${PYTHON_VERSION}"
uv venv --python "${PYTHON_VERSION}"
uv sync --group dev

echo "==> Installing pre-commit hooks"
uv run pre-commit install

echo "==> Creating the export directory for the ds-template hand-off"
mkdir -p data/exports

echo "==> Building image and starting Docker services"
docker compose up -d --build

echo ""
echo "Done! Services running:"
echo "  Airflow UI  →  http://localhost:8080  (admin / admin)"
echo "  Postgres    →  localhost:5432"
echo ""
echo "Next:"
echo "  make help     list every command"
echo "  make dbt-run  build the dbt models"
echo "  make export   write the marts out downstream"

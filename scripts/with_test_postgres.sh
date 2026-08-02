#!/usr/bin/env bash
# Run a command against a throwaway Postgres, then clean it up.
#
#   ./scripts/with_test_postgres.sh uv run pytest tests/test_exporters/...
#
# Deliberately separate from the docker compose stack: these tests create and
# drop tables, and should not touch a warehouse you have data in. The container
# is removed on exit, including on failure or Ctrl-C.
set -euo pipefail

CONTAINER_NAME="${TEST_PG_NAME:-de-template-testdb}"
HOST_PORT="${TEST_PG_PORT:-55432}"
IMAGE="${TEST_PG_IMAGE:-postgres:16}"
PASSWORD="test"

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and try again." >&2
  exit 1
fi

cleanup
echo "==> Starting throwaway Postgres (${IMAGE}) on port ${HOST_PORT}"
docker run -d --name "${CONTAINER_NAME}" \
  -e POSTGRES_PASSWORD="${PASSWORD}" \
  -p "${HOST_PORT}:5432" \
  "${IMAGE}" >/dev/null

echo -n "==> Waiting for it to accept connections"
for _ in $(seq 1 60); do
  if docker exec "${CONTAINER_NAME}" pg_isready -U postgres >/dev/null 2>&1; then
    echo " ready"
    break
  fi
  echo -n "."
  sleep 1
done

if ! docker exec "${CONTAINER_NAME}" pg_isready -U postgres >/dev/null 2>&1; then
  echo " timed out" >&2
  docker logs "${CONTAINER_NAME}" >&2
  exit 1
fi

URL="postgresql+psycopg2://postgres:${PASSWORD}@localhost:${HOST_PORT}/postgres"
export DE_TEST_POSTGRES_URL="${URL}"
export DE_DEMO_POSTGRES_URL="${URL}"

echo "==> Running: $*"
"$@"

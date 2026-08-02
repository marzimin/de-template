"""Shared fixtures.

Warehouse-touching code is tested against an in-memory SQLite database where
the SQL is portable, and against mocks where it is not — ``CREATE SCHEMA`` and
the loader's Postgres-flavoured DDL have no SQLite equivalent.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_root() -> Path:
    """The repository root, for tests that read tracked files."""
    return PROJECT_ROOT


@pytest.fixture
def warehouse_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the WAREHOUSE_*/POSTGRES_* variables the engine builder requires."""
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("WAREHOUSE_USER", "de_user")
    monkeypatch.setenv("WAREHOUSE_PASSWORD", "de_password")
    monkeypatch.setenv("WAREHOUSE_DB", "warehouse")

from unittest.mock import MagicMock, patch

import pytest

from loaders.postgres_loader import PostgresLoader


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


def test_load_returns_row_count(mock_engine):
    engine, _ = mock_engine
    loader = PostgresLoader(engine=engine)

    result = loader.load([{"id": "1", "name": "alice"}], table="raw.users")

    assert result == 1


def test_load_returns_zero_for_empty_records(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    result = loader.load([], table="raw.users")

    assert result == 0
    engine.begin.assert_not_called()


def test_load_creates_schema_and_table(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load([{"col": "val"}], table="raw.items")

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("CREATE SCHEMA IF NOT EXISTS raw" in s for s in executed_sql)
    assert any("CREATE TABLE IF NOT EXISTS raw.items" in s for s in executed_sql)


def test_load_defaults_to_raw_schema_when_no_schema_given(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load([{"col": "val"}], table="items")

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS raw.items" in s for s in executed_sql)


def test_engine_from_env_uses_env_vars(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "myhost")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "myuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", "mypass")
    monkeypatch.setenv("POSTGRES_DB", "mydb")

    with patch("loaders.postgres_loader.create_engine") as mock_create:
        PostgresLoader()
        mock_create.assert_called_once_with(
            "postgresql+psycopg2://myuser:mypass@myhost:5433/mydb"
        )

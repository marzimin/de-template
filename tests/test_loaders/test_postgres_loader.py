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


def test_load_normalizes_column_names(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load(
        [{"Order ID": "1", "created-at": "2026-06-13"}],
        table="raw.items",
    )

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    insert_args = conn.execute.call_args_list[-1].args

    assert any("order_id TEXT" in s for s in executed_sql)
    assert any("created_at TEXT" in s for s in executed_sql)
    assert "INSERT INTO raw.items (order_id, created_at)" in str(insert_args[0])
    assert insert_args[1] == [{"order_id": "1", "created_at": "2026-06-13"}]


def test_load_uses_all_columns_across_records(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load(
        [{"id": "1"}, {"id": "2", "name": "alice"}],
        table="raw.items",
    )

    insert_args = conn.execute.call_args_list[-1].args
    assert "INSERT INTO raw.items (id, name)" in str(insert_args[0])
    assert insert_args[1] == [{"id": "1", "name": None}, {"id": "2", "name": "alice"}]


def test_load_rejects_invalid_table_name(mock_engine):
    engine, _ = mock_engine
    loader = PostgresLoader(engine=engine)

    with pytest.raises(ValueError, match="Invalid table name"):
        loader.load([{"id": "1"}], table="raw.user-events")


def test_load_rejects_duplicate_normalized_column_names(mock_engine):
    engine, _ = mock_engine
    loader = PostgresLoader(engine=engine)

    with pytest.raises(ValueError, match="normalize to the same identifier"):
        loader.load([{"Order ID": "1", "order-id": "1"}], table="raw.items")


def test_load_defaults_to_raw_schema_when_no_schema_given(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load([{"col": "val"}], table="items")

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS raw.items" in s for s in executed_sql)


def test_engine_from_env_uses_env_vars(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "myhost")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("WAREHOUSE_USER", "myuser")
    monkeypatch.setenv("WAREHOUSE_PASSWORD", "mypass")
    monkeypatch.setenv("WAREHOUSE_DB", "mydb")

    with patch("loaders.postgres_loader.create_engine") as mock_create:
        PostgresLoader()
        url = mock_create.call_args.args[0]
        assert str(url) == "postgresql+psycopg2://myuser:***@myhost:5433/mydb"
        assert url.password == "mypass"

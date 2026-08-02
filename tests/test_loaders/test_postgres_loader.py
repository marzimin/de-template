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


def test_append_mode_does_not_clear_the_table(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load([{"id": "1"}], table="raw.items")

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert not any("DELETE FROM" in s for s in executed_sql)


def test_replace_mode_clears_the_table_before_inserting(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine, mode="replace")

    loader.load([{"id": "1"}], table="raw.items")

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    delete_index = next(i for i, s in enumerate(executed_sql) if "DELETE FROM" in s)
    insert_index = next(i for i, s in enumerate(executed_sql) if "INSERT INTO" in s)

    assert "DELETE FROM raw.items" in executed_sql[delete_index]
    assert delete_index < insert_index
    # Both run inside one transaction, so a failed insert cannot leave the
    # table empty.
    assert engine.begin.call_count == 1


def test_mode_can_be_overridden_per_call(mock_engine):
    engine, conn = mock_engine
    loader = PostgresLoader(engine=engine)

    loader.load([{"id": "1"}], table="raw.items", mode="replace")

    executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("DELETE FROM raw.items" in s for s in executed_sql)


def test_replace_mode_leaves_the_table_alone_when_there_is_nothing_to_load(
    mock_engine,
):
    """An empty extract must not wipe the table.

    Otherwise a transient API failure returning [] turns into data loss, and
    the next dbt run builds marts from nothing.
    """
    engine, _ = mock_engine
    loader = PostgresLoader(engine=engine, mode="replace")

    assert loader.load([], table="raw.items") == 0
    engine.begin.assert_not_called()


def test_rejects_an_unsupported_load_mode(mock_engine):
    engine, _ = mock_engine

    with pytest.raises(ValueError, match="Unsupported load mode"):
        PostgresLoader(engine=engine, mode="upsert")


def test_configured_load_modes_are_supported():
    """cfg/config.yaml must not name a mode the loader will reject at run time."""
    from core.config import read_config

    for source in read_config()["sources"].values():
        assert source.get("load_mode", "append") in ("append", "replace")


def test_builds_its_engine_from_the_environment_when_not_given_one():
    """Engine construction lives in core.warehouse, shared with the exporter.

    The URL itself is covered in tests/test_core/test_warehouse.py; this only
    checks the loader delegates rather than building its own.
    """
    with patch("loaders.postgres_loader.engine_from_env") as mock_engine_from_env:
        loader = PostgresLoader()

    mock_engine_from_env.assert_called_once_with()
    assert loader.engine is mock_engine_from_env.return_value

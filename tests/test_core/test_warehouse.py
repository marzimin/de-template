from unittest.mock import patch

import pytest

from core.warehouse import (
    engine_from_env,
    normalize_column_name,
    split_relation,
    validate_identifier,
)


def test_engine_from_env_builds_the_url_and_keeps_the_password_off_the_repr(
    warehouse_env,
):
    with patch("core.warehouse.create_engine") as mock_create:
        engine_from_env()

    url = mock_create.call_args.args[0]
    assert str(url) == "postgresql+psycopg2://de_user:***@localhost:5432/warehouse"
    assert url.password == "de_password"


def test_engine_from_env_requires_the_warehouse_variables(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_USER", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")

    with pytest.raises(KeyError):
        engine_from_env()


@pytest.mark.parametrize("identifier", ["raw", "_private", "order_items_2"])
def test_accepts_valid_identifiers(identifier):
    assert validate_identifier(identifier, "table") == identifier


@pytest.mark.parametrize(
    "identifier",
    ["Order", "user-events", "2fast", "drop table", "raw;delete", ""],
)
def test_rejects_invalid_identifiers(identifier):
    with pytest.raises(ValueError, match="Invalid table name"):
        validate_identifier(identifier, "table")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Order ID", "order_id"),
        ("created-at", "created_at"),
        ("  MixedCase  ", "mixedcase"),
        ("2020_total", "_2020_total"),
        ("a..b", "a_b"),
    ],
)
def test_normalizes_column_names(name, expected):
    assert normalize_column_name(name) == expected


def test_rejects_a_column_name_that_normalizes_to_nothing():
    with pytest.raises(ValueError, match="cannot be normalized"):
        normalize_column_name("!!!")


def test_splits_a_qualified_relation():
    assert split_relation("marts.example_items") == ("marts", "example_items")


def test_applies_the_default_schema_to_a_bare_table():
    assert split_relation("example_items", "marts") == ("marts", "example_items")


def test_rejects_an_over_qualified_relation():
    with pytest.raises(ValueError, match="'table' or 'schema.table'"):
        split_relation("db.schema.table")

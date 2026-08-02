import csv

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from exporters.mart_exporter import MartExporter


@pytest.fixture
def marts_engine():
    """SQLite standing in for the warehouse, with a `marts` schema attached.

    SQLite has no CREATE SCHEMA, but an ATTACHed database is addressed exactly
    like one — `marts.example_items` resolves the same way it does in Postgres,
    which is all the exporter's SQL depends on. StaticPool keeps every checkout
    on the one connection that holds the attachment.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS marts"))
        conn.execute(
            text(
                "CREATE TABLE marts.example_items "
                "(item_id TEXT, item_name TEXT, item_name_length INTEGER)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO marts.example_items VALUES "
                "('1', 'widget', 6), ('2', 'gadget', 6)"
            )
        )
    return engine


@pytest.fixture
def empty_marts_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS marts"))
        conn.execute(text("CREATE TABLE marts.empty_items (item_id TEXT)"))
    return engine


def test_exports_rows_to_csv(tmp_path, marts_engine):
    exporter = MartExporter(
        "marts.example_items", destination=tmp_path, engine=marts_engine
    )

    path = exporter.export()

    assert path == tmp_path / "example_items.csv"
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {"item_id": "1", "item_name": "widget", "item_name_length": "6"},
        {"item_id": "2", "item_name": "gadget", "item_name_length": "6"},
    ]


def test_creates_the_destination_directory(tmp_path, marts_engine):
    destination = tmp_path / "does" / "not" / "exist"
    exporter = MartExporter(
        "marts.example_items", destination=destination, engine=marts_engine
    )

    path = exporter.export()

    assert path.exists()


def test_file_name_defaults_to_the_table_name(tmp_path, marts_engine):
    exporter = MartExporter(
        "marts.example_items", destination=tmp_path, engine=marts_engine
    )

    assert exporter.output_path.name == "example_items.csv"


def test_file_name_can_be_overridden(tmp_path, marts_engine):
    exporter = MartExporter(
        "marts.example_items",
        destination=tmp_path,
        file_name="items_for_modelling.csv",
        engine=marts_engine,
    )

    assert exporter.export().name == "items_for_modelling.csv"


def test_unqualified_relation_uses_the_default_schema(tmp_path, marts_engine):
    exporter = MartExporter(
        "example_items",
        destination=tmp_path,
        default_schema="marts",
        engine=marts_engine,
    )

    assert exporter.schema == "marts"
    assert len(exporter.export().read_text(encoding="utf-8").splitlines()) == 3


def test_empty_relation_still_writes_a_header(tmp_path, empty_marts_engine):
    """An empty mart must produce a header-only file, not an empty one.

    pandas raises EmptyDataError on a zero-byte CSV, so the DS project would
    fail with a parser error rather than an obvious "no rows yet".
    """
    exporter = MartExporter(
        "marts.empty_items", destination=tmp_path, engine=empty_marts_engine
    )

    path = exporter.export()

    assert path.read_text(encoding="utf-8").strip() == "item_id"


def test_exports_to_parquet(tmp_path, marts_engine):
    pq = pytest.importorskip("pyarrow.parquet")

    exporter = MartExporter(
        "marts.example_items",
        destination=tmp_path,
        export_format="parquet",
        engine=marts_engine,
    )

    path = exporter.export()

    assert path.name == "example_items.parquet"
    table = pq.read_table(path)
    assert table.num_rows == 2
    assert set(table.column_names) == {"item_id", "item_name", "item_name_length"}


def test_empty_parquet_export_keeps_the_columns(tmp_path, empty_marts_engine):
    pq = pytest.importorskip("pyarrow.parquet")

    exporter = MartExporter(
        "marts.empty_items",
        destination=tmp_path,
        export_format="parquet",
        engine=empty_marts_engine,
    )

    table = pq.read_table(exporter.export())

    assert table.num_rows == 0
    assert table.column_names == ["item_id"]


def test_rejects_an_unsupported_format(tmp_path, marts_engine):
    with pytest.raises(ValueError, match="Unsupported export format"):
        MartExporter(
            "marts.example_items",
            destination=tmp_path,
            export_format="xlsx",
            engine=marts_engine,
        )


def test_rejects_an_injection_attempt_in_the_relation(tmp_path, marts_engine):
    with pytest.raises(ValueError, match="Invalid table name"):
        MartExporter(
            "marts.items; DROP TABLE users",
            destination=tmp_path,
            engine=marts_engine,
        )

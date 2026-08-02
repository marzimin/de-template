"""End-to-end type fidelity against a real Postgres.

The unit tests in test_serialisation.py cover the conversions in isolation, but
they cannot tell you what psycopg2 actually hands over for a ``bytea`` or a
``jsonb`` — that is a property of the driver, not of our code. This module
exports a table containing every type a dbt mart can plausibly produce and
checks what lands in the file.

Skipped unless a database is reachable. Point it at one with:

    DE_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:test@localhost:55432/postgres

or run `make test-integration`, which starts a throwaway container for you.
"""

import csv
import json
import os

import pytest
from sqlalchemy import create_engine, text

from exporters.mart_exporter import MartExporter

DATABASE_URL = os.getenv("DE_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set DE_TEST_POSTGRES_URL to run the Postgres type-fidelity tests",
)

KITCHEN_SINK_DDL = """
CREATE TABLE marts.kitchen_sink (
    c_int        integer,
    c_bigint     bigint,
    c_numeric    numeric(12,4),
    c_float      double precision,
    c_bool       boolean,
    c_text       text,
    c_empty_text text,
    c_nullable   text,
    c_date       date,
    c_ts         timestamp,
    c_tstz       timestamptz,
    c_uuid       uuid,
    c_json       jsonb,
    c_array      integer[],
    c_bytea      bytea,
    c_interval   interval
)
"""

KITCHEN_SINK_ROW = """
INSERT INTO marts.kitchen_sink VALUES (
    42, 9223372036854775807, 1234.5678, 3.14159, true,
    'has, comma and "quote" and' || chr(10) || 'newline', '', NULL,
    '2024-03-01', '2024-03-01 12:34:56', '2024-03-01 12:34:56+00',
    '11111111-2222-3333-4444-555555555555',
    '{"a": 1, "b": [true, null]}', '{1,2,3}',
    '\\xdeadbeef'::bytea, '1 day 02:03:04'
)
"""


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS marts"))
        conn.execute(text("DROP TABLE IF EXISTS marts.kitchen_sink"))
        conn.execute(text(KITCHEN_SINK_DDL))
        conn.execute(text(KITCHEN_SINK_ROW))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS marts.kitchen_sink"))
    engine.dispose()


@pytest.fixture(scope="module")
def exported_row(engine, tmp_path_factory):
    destination = tmp_path_factory.mktemp("export")
    path = MartExporter(
        "marts.kitchen_sink", destination=destination, engine=engine
    ).export()
    with open(path, newline="", encoding="utf-8") as handle:
        return next(iter(csv.DictReader(handle)))


def test_integers_and_floats_are_plain(exported_row):
    assert exported_row["c_int"] == "42"
    assert exported_row["c_bigint"] == "9223372036854775807"
    assert exported_row["c_float"] == "3.14159"


def test_numeric_keeps_full_precision(exported_row):
    assert exported_row["c_numeric"] == "1234.5678"


def test_boolean_is_readable_as_a_boolean(exported_row):
    assert exported_row["c_bool"] == "True"


def test_text_survives_commas_quotes_and_newlines(exported_row):
    assert exported_row["c_text"] == 'has, comma and "quote" and\nnewline'


def test_dates_and_timestamps_are_iso_8601(exported_row):
    assert exported_row["c_date"] == "2024-03-01"
    assert exported_row["c_ts"] == "2024-03-01T12:34:56"
    assert exported_row["c_tstz"] == "2024-03-01T12:34:56+00:00"


def test_uuid_is_the_canonical_form(exported_row):
    assert exported_row["c_uuid"] == "11111111-2222-3333-4444-555555555555"


def test_jsonb_is_valid_json(exported_row):
    """psycopg2 returns a parsed dict; str() would give a Python repr."""
    assert json.loads(exported_row["c_json"]) == {"a": 1, "b": [True, None]}


def test_arrays_are_valid_json(exported_row):
    assert json.loads(exported_row["c_array"]) == [1, 2, 3]


def test_bytea_is_recoverable_hex(exported_row):
    """The regression this module exists for: str(memoryview) loses the bytes."""
    assert exported_row["c_bytea"] == "deadbeef"
    assert bytes.fromhex(exported_row["c_bytea"]) == b"\xde\xad\xbe\xef"


def test_interval_is_an_iso_8601_duration(exported_row):
    assert exported_row["c_interval"] == "P1DT2H3M4S"


def test_null_is_empty(exported_row):
    assert exported_row["c_nullable"] == ""


def test_pandas_can_read_the_whole_file(engine, tmp_path):
    """The end product has to be readable by ds-template."""
    pd = pytest.importorskip("pandas")

    path = MartExporter(
        "marts.kitchen_sink", destination=tmp_path, engine=engine
    ).export()
    frame = pd.read_csv(path)

    assert len(frame) == 1
    assert frame["c_int"].dtype.kind == "i"
    assert frame["c_numeric"].dtype.kind == "f"
    # "True"/"False" is read back as a real boolean, so a flag column is
    # immediately usable as a numeric feature.
    assert frame["c_bool"].dtype == bool


def test_parquet_export_handles_every_type(engine, tmp_path):
    """Arrow rejects UUID outright, which used to fail the whole export."""
    pq = pytest.importorskip("pyarrow.parquet")

    path = MartExporter(
        "marts.kitchen_sink",
        destination=tmp_path,
        export_format="parquet",
        engine=engine,
    ).export()
    table = pq.read_table(path)

    assert table.num_rows == 1
    types = dict(zip(table.column_names, table.schema.types, strict=True))
    # Parquet's whole point is keeping types, so check they survived.
    assert str(types["c_numeric"]).startswith("decimal")
    assert str(types["c_date"]).startswith("date")
    assert str(types["c_bytea"]) == "binary"
    assert str(types["c_interval"]).startswith("duration")


def test_null_sentinel_distinguishes_null_from_empty_string(engine, tmp_path):
    path = MartExporter(
        "marts.kitchen_sink",
        destination=tmp_path,
        file_name="sentinel.csv",
        engine=engine,
        null_sentinel="\\N",
    ).export()
    with open(path, newline="", encoding="utf-8") as handle:
        row = next(iter(csv.DictReader(handle)))

    assert row["c_nullable"] == "\\N"
    assert row["c_empty_text"] == ""

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from exporters.serialisation import (
    csv_row,
    iso_duration,
    to_csv_value,
    to_parquet_value,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Scalars pass through as their obvious text form.
        (42, "42"),
        (3.14159, "3.14159"),
        ("plain", "plain"),
        ("", ""),
        # bool before int: "True" round-trips to a real bool dtype in pandas,
        # which "1" does not.
        (True, "True"),
        (False, "False"),
        # Exact decimal text, not the float approximation.
        (Decimal("1234.5678"), "1234.5678"),
        (Decimal("0.1"), "0.1"),
        # ISO 8601 throughout.
        (date(2024, 3, 1), "2024-03-01"),
        (datetime(2024, 3, 1, 12, 34, 56), "2024-03-01T12:34:56"),
        (
            datetime(2024, 3, 1, 12, 34, 56, tzinfo=UTC),
            "2024-03-01T12:34:56+00:00",
        ),
        (time(12, 34, 56), "12:34:56"),
        (
            UUID("11111111-2222-3333-4444-555555555555"),
            "11111111-2222-3333-4444-555555555555",
        ),
        # Binary as hex, not str(memoryview).
        (b"\xde\xad\xbe\xef", "deadbeef"),
        (bytearray(b"\xde\xad\xbe\xef"), "deadbeef"),
        (memoryview(b"\xde\xad\xbe\xef"), "deadbeef"),
    ],
)
def test_converts_scalars(value, expected):
    assert to_csv_value(value) == expected


def test_null_becomes_the_sentinel():
    assert to_csv_value(None) == ""
    assert to_csv_value(None, null_sentinel="\\N") == "\\N"


def test_binary_survives_the_round_trip():
    """str() on a memoryview gives '<memory at 0x...>' and loses the bytes.

    Worse, the address differs between runs, so two exports of identical data
    would diff as changed.
    """
    original = b"\x00\x01\xfe\xff"

    assert bytes.fromhex(to_csv_value(memoryview(original))) == original


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"a": 1, "b": [True, None]}, {"a": 1, "b": [True, None]}),
        ([1, 2, 3], [1, 2, 3]),
        ((1, 2, 3), [1, 2, 3]),
        ([], []),
        ({}, {}),
        (
            {"nested": {"deep": [1, {"x": None}]}},
            {"nested": {"deep": [1, {"x": None}]}},
        ),
    ],
)
def test_structures_become_valid_json(value, expected):
    """str() on a dict gives a Python repr that no JSON parser accepts."""
    assert json.loads(to_csv_value(value)) == expected


def test_json_handles_values_json_cannot_encode_itself():
    """Postgres arrays of dates arrive as lists of date objects."""
    encoded = to_csv_value([date(2024, 3, 1), date(2024, 3, 2)])

    assert json.loads(encoded) == ["2024-03-01", "2024-03-02"]


def test_json_keeps_non_ascii_readable():
    assert to_csv_value({"name": "café"}) == '{"name": "café"}'


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(days=1, hours=2, minutes=3, seconds=4), "P1DT2H3M4S"),
        (timedelta(days=1), "P1D"),
        (timedelta(hours=2), "PT2H"),
        (timedelta(seconds=30), "PT30S"),
        (timedelta(0), "PT0S"),
        (timedelta(days=-1), "-P1D"),
        (timedelta(milliseconds=1500), "PT1.5S"),
    ],
)
def test_durations_are_iso_8601(delta, expected):
    assert iso_duration(delta) == expected
    assert to_csv_value(delta) == expected


def test_csv_row_fills_missing_columns_with_the_sentinel():
    row = csv_row({"a": 1}, ["a", "b"], null_sentinel="NULL")

    assert row == {"a": "1", "b": "NULL"}


def test_csv_row_follows_the_column_order_given():
    assert list(csv_row({"b": 2, "a": 1}, ["a", "b"])) == ["a", "b"]


class _Unknown:
    def __str__(self) -> str:
        return "fallback"


def test_unknown_types_fall_back_to_str():
    assert to_csv_value(_Unknown()) == "fallback"


# --- Parquet ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Left alone: Arrow infers these correctly and keeps the type.
        (42, 42),
        (3.14, 3.14),
        (True, True),
        ("text", "text"),
        (None, None),
        (Decimal("1.5"), Decimal("1.5")),
        (date(2024, 3, 1), date(2024, 3, 1)),
        (timedelta(days=1), timedelta(days=1)),
        ([1, 2, 3], [1, 2, 3]),
    ],
)
def test_parquet_passes_through_what_arrow_understands(value, expected):
    assert to_parquet_value(value) == expected


def test_parquet_converts_uuid_which_arrow_cannot_infer():
    """Arrow raises ArrowInvalid on a UUID, failing the whole export."""
    assert (
        to_parquet_value(UUID("11111111-2222-3333-4444-555555555555"))
        == "11111111-2222-3333-4444-555555555555"
    )


def test_parquet_converts_memoryview_to_bytes():
    assert to_parquet_value(memoryview(b"\xde\xad")) == b"\xde\xad"


def test_parquet_encodes_mappings_as_json():
    """Mappings are stored as JSON text rather than Arrow structs.

    Struct inference is built from the first rows and fails on a later row with
    different keys.
    """
    assert json.loads(to_parquet_value({"a": 1})) == {"a": 1}

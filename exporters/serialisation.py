"""Convert database values into something a file can hold without losing them.

A database driver hands back rich Python objects — ``Decimal``, ``datetime``,
``UUID``, ``memoryview``, parsed JSON. CSV holds only text, so every one of them
has to become a string. Left to its own devices :mod:`csv` calls ``str()``, and
``str()`` on a ``memoryview`` is ``<memory at 0x7f3c...>``: the bytes are gone,
and the address changes between runs so two exports of identical data diff as
changed.

This module decides those conversions explicitly, preferring formats a consumer
can parse back: ISO 8601 for dates and durations, JSON for structures, hex for
binary.
"""

import json
from collections.abc import Mapping, Sequence, Set
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

#: Written for a SQL NULL by default. Empty is what pandas reads as NaN with no
#: extra configuration — the reference downstream project, ds-template, reads
#: it this way out of the box. The cost is that a genuine empty string becomes
#: indistinguishable from NULL — set ``exports.null_sentinel`` if you need to
#: tell them apart.
DEFAULT_NULL_SENTINEL = ""


def iso_duration(delta: timedelta) -> str:
    """Format a timedelta as an ISO 8601 duration.

    ``str(timedelta)`` produces ``"1 day, 2:03:04"``, which no standard parser
    reads. This produces ``"P1DT2H3M4S"``, which they do.

    Args:
        delta: The duration to format.

    Returns:
        An ISO 8601 duration string, negated with a leading ``-`` if needed.
    """
    total_seconds = delta.total_seconds()
    sign = "-" if total_seconds < 0 else ""
    remaining = abs(total_seconds)

    days, remaining = divmod(remaining, 86_400)
    hours, remaining = divmod(remaining, 3_600)
    minutes, seconds = divmod(remaining, 60)

    result = f"{sign}P{int(days)}D" if days else f"{sign}P"
    if hours or minutes or seconds:
        result += "T"
        if hours:
            result += f"{int(hours)}H"
        if minutes:
            result += f"{int(minutes)}M"
        if seconds:
            # Keep sub-second precision only when there is any, so whole
            # seconds do not gain a misleading ".000000".
            formatted = f"{seconds:.6f}".rstrip("0").rstrip(".")
            result += f"{formatted}S"
    elif not days:
        result += "T0S"

    return result


def _json_default(value: Any) -> str:
    """Render values json.dumps cannot handle itself, inside a JSON document."""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return iso_duration(value)
    if isinstance(value, Decimal | UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    return str(value)


def to_csv_value(value: Any, null_sentinel: str = DEFAULT_NULL_SENTINEL) -> str:
    """Convert one database value to its CSV representation.

    Args:
        value: The value as the driver returned it.
        null_sentinel: What to write for ``None``.

    Returns:
        A string. The :mod:`csv` writer handles quoting, so embedded commas,
        quotes, and newlines need no special treatment here.
    """
    if value is None:
        return null_sentinel

    # Checked before int: bool is a subclass of int, and "True" round-trips to a
    # real boolean dtype in pandas whereas "1" does not.
    if isinstance(value, bool):
        return str(value)

    if isinstance(value, str):
        return value

    # Exact decimal text. pandas will still widen it to float64 on read, but the
    # file itself keeps the precision the warehouse had.
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()

    if isinstance(value, datetime | date | time):
        return value.isoformat()

    if isinstance(value, timedelta):
        return iso_duration(value)

    if isinstance(value, UUID):
        return str(value)

    # JSON and array columns arrive already parsed. json.dumps gives valid JSON;
    # str() would give a Python repr with single quotes that no JSON parser
    # accepts. str is excluded above, and Mapping/Sequence/Set covers dict,
    # list, tuple, and set without catching bytes.
    if isinstance(value, Mapping | Set) or (
        isinstance(value, Sequence) and not isinstance(value, str)
    ):
        return json.dumps(value, default=_json_default, ensure_ascii=False)

    return str(value)


def to_parquet_value(value: Any) -> Any:
    """Convert one database value into something PyArrow can infer a type for.

    Parquet keeps types, so most values are passed through untouched. Only the
    ones Arrow's type inference rejects outright are converted — a ``UUID``
    raises ``ArrowInvalid: did not recognize Python value type``, which fails
    the whole export rather than just that column.

    Args:
        value: The value as the driver returned it.

    Returns:
        The value, or an Arrow-representable stand-in.
    """
    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, memoryview | bytearray):
        return bytes(value)

    # Structures become JSON text rather than Arrow structs. Inference builds
    # the struct from the first rows, so a later row with different keys — or a
    # column that is all NULL in the first chunk — fails mid-write.
    if isinstance(value, Mapping | Set):
        return json.dumps(value, default=_json_default, ensure_ascii=False)

    return value


def csv_row(
    row: Mapping[str, Any],
    columns: Sequence[str],
    null_sentinel: str = DEFAULT_NULL_SENTINEL,
) -> dict[str, str]:
    """Convert a whole row for CSV output."""
    return {column: to_csv_value(row.get(column), null_sentinel) for column in columns}


def parquet_row(row: Mapping[str, Any], columns: Sequence[str]) -> dict[str, Any]:
    """Convert a whole row for Parquet output."""
    return {column: to_parquet_value(row.get(column)) for column in columns}

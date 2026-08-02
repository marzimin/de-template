"""End-to-end demonstration of the warehouse → file → DS hand-off.

Builds two marts in the warehouse, exports them with the real exporter, and
checks the results are what ds-template needs. Run it with::

    make demo-handoff

The two marts make different points:

``demo_customer_events``
    Every awkward type a dbt mart can produce — uuid, jsonb, arrays, bytea,
    interval, timestamptz. Proves the export is *faithful*: nothing is lost or
    rendered unparseable on the way to disk.

``demo_customer_features``
    A training-shaped mart: numeric features and a target, nothing else. Proves
    the export is *usable*: ds-template can read this file and train on it
    without touching Python.

That difference is the lesson. A mart that round-trips correctly is not
automatically a mart a model can consume — shape it for its reader in dbt.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.warehouse import engine_from_env
from exporters.mart_exporter import MartExporter

EVENTS_TABLE = "marts.demo_customer_events"
FEATURES_TABLE = "marts.demo_customer_features"
TARGET_COLUMN = "CHURNED"

# A mart with the types that break a naive exporter.
EVENTS_DDL = """
CREATE TABLE marts.demo_customer_events (
    event_id      uuid,
    customer_id   integer,
    occurred_at   timestamptz,
    event_type    text,
    amount        numeric(10,2),
    is_refund     boolean,
    session_len   interval,
    payload       jsonb,
    tag_ids       integer[],
    signature     bytea
)
"""

EVENTS_ROWS = """
INSERT INTO marts.demo_customer_events
SELECT
    ('11111111-2222-3333-4444-' || lpad(i::text, 12, '0'))::uuid,
    i % 50,
    timestamptz '2024-03-01 09:00:00+00' + (i || ' hours')::interval,
    (array['purchase', 'refund', 'view'])[1 + (i % 3)],
    round((i * 7.31)::numeric, 2),
    (i % 3 = 1),
    ((i % 90) || ' minutes')::interval,
    jsonb_build_object('channel', 'web', 'items', jsonb_build_array(i, i + 1)),
    array[i % 5, i % 7],
    decode(lpad(to_hex(i), 8, '0'), 'hex')
FROM generate_series(1, 100) AS i
"""

# A mart shaped for modelling: numeric features, a target, no nulls.
FEATURES_DDL = """
CREATE TABLE marts.demo_customer_features (
    tenure_days     integer,
    monthly_spend   numeric(10,2),
    support_tickets integer,
    is_premium      boolean,
    churned         integer
)
"""

FEATURES_ROWS = """
INSERT INTO marts.demo_customer_features
SELECT
    tenure,
    spend,
    tickets,
    premium,
    -- A learnable signal: short tenure and many tickets predict churn.
    CASE WHEN tenure < 180 AND tickets > 3 THEN 1
         WHEN tenure < 90 THEN 1
         ELSE 0 END
FROM (
    SELECT
        (i * 13) % 730                      AS tenure,
        round(((i * 17) % 400)::numeric, 2) AS spend,
        (i * 3) % 9                         AS tickets,
        (i % 4 = 0)                         AS premium
    FROM generate_series(1, 400) AS i
) AS raw_features
"""


def build_demo_marts(engine: Engine) -> None:
    """Create and populate the two demonstration marts, replacing any existing."""
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS marts"))
        for table, ddl, rows in (
            (EVENTS_TABLE, EVENTS_DDL, EVENTS_ROWS),
            (FEATURES_TABLE, FEATURES_DDL, FEATURES_ROWS),
        ):
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.execute(text(ddl))
            conn.execute(text(rows))


def normalise_column_name(column_name: str) -> str:
    """Normalise a column name the way ds-template does on read.

    Reproduced rather than imported: that project is a separate repository and
    may not be checked out beside this one. Kept identical to its
    ``src.schemas.normalise_column_name``.
    """
    import re

    return re.sub(r"[^A-Z0-9]+", "_", column_name.upper()).strip("_")


def check_fidelity(path: Path) -> list[tuple[str, bool, str]]:
    """Verify the rich-typed export lost nothing on the way to disk."""
    import csv
    import json

    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    row = rows[0]

    return [
        ("rows exported", len(rows) == 100, f"{len(rows)} rows"),
        (
            "bytea is recoverable hex",
            bytes.fromhex(row["signature"]) == bytes.fromhex("00000001"),
            row["signature"],
        ),
        (
            "jsonb parses as JSON",
            json.loads(row["payload"])["channel"] == "web",
            row["payload"],
        ),
        ("array parses as JSON", json.loads(row["tag_ids"]) == [1, 1], row["tag_ids"]),
        ("interval is ISO 8601", row["session_len"] == "PT1M", row["session_len"]),
        (
            "timestamptz is ISO 8601",
            row["occurred_at"].startswith("2024-03-01T10:00:00"),
            row["occurred_at"],
        ),
        ("numeric keeps precision", row["amount"] == "7.31", row["amount"]),
        ("uuid is canonical", row["event_id"].count("-") == 4, row["event_id"]),
    ]


def check_ds_readable(path: Path) -> list[tuple[str, bool, str]]:
    """Verify the training mart meets ds-template's stated requirements.

    That project needs numeric features with no missing values by training time,
    and normalises column names to upper case on read.
    """
    import pandas as pd

    frame = pd.read_csv(path)
    frame.columns = pd.Index([normalise_column_name(c) for c in frame.columns])

    features = frame.drop(columns=[TARGET_COLUMN], errors="ignore")
    non_numeric = [
        c for c in features.columns if not pd.api.types.is_numeric_dtype(features[c])
    ]
    with_nulls = [c for c in frame.columns if bool(frame[c].isna().any())]

    return [
        ("pandas reads the file", len(frame) == 400, f"{len(frame)} rows"),
        (
            "columns normalise to upper case",
            all(c == c.upper() for c in frame.columns),
            ", ".join(frame.columns),
        ),
        (
            f"target {TARGET_COLUMN} is present",
            TARGET_COLUMN in frame.columns,
            TARGET_COLUMN,
        ),
        ("every feature is numeric", not non_numeric, f"non-numeric: {non_numeric}"),
        ("no missing values", not with_nulls, f"with nulls: {with_nulls}"),
        (
            "target is binary",
            sorted(frame[TARGET_COLUMN].unique().tolist()) == [0, 1],
            str(sorted(frame[TARGET_COLUMN].unique().tolist())),
        ),
    ]


def report(title: str, checks: list[tuple[str, bool, str]]) -> bool:
    """Print a check block and return whether all of it passed."""
    print(f"\n{title}")
    print("-" * len(title))
    for label, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {label:<32} {detail}")
    return all(passed for _, passed, _ in checks)


def resolve_engine() -> Engine:
    """Connect via DE_DEMO_POSTGRES_URL, or the usual WAREHOUSE_* variables."""
    url = os.getenv("DE_DEMO_POSTGRES_URL")
    return create_engine(url) if url else engine_from_env()


def main() -> None:
    """Run the demonstration and exit non-zero if any check fails."""
    parser = argparse.ArgumentParser(
        prog="demo-handoff",
        description=(
            "Build two demo marts, export them, and verify the output is "
            "faithful and readable by ds-template."
        ),
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=None,
        help="Where to write the files. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the demo marts in the warehouse instead of dropping them.",
    )
    args = parser.parse_args()

    destination = args.destination or Path(tempfile.mkdtemp(prefix="de-demo-"))
    engine = resolve_engine()

    print(f"Building demo marts in {engine.url.render_as_string()}")
    build_demo_marts(engine)

    exports: dict[str, Any] = {}
    for table in (EVENTS_TABLE, FEATURES_TABLE):
        exports[table] = MartExporter(
            table, destination=destination, engine=engine
        ).export()
        print(f"  exported {table} -> {exports[table]}")

    passed = report(
        "1. Type fidelity — did anything get lost or mangled?",
        check_fidelity(exports[EVENTS_TABLE]),
    )
    passed &= report(
        "2. DS readability — can ds-template train on this?",
        check_ds_readable(exports[FEATURES_TABLE]),
    )

    if not args.keep:
        with engine.begin() as conn:
            for table in (EVENTS_TABLE, FEATURES_TABLE):
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

    print(f"\n{'All checks passed.' if passed else 'FAILURES — see above.'}")
    if passed:
        print(
            "\nTo train on it, copy "
            f"{exports[FEATURES_TABLE].name} into ds-template/data/raw/ "
            "(or set DS_DATA_RAW_DIR) and set its cfg/config.yaml to:\n"
            "\n  data:"
            '\n    input_file: "demo_customer_features.csv"'
            f'\n  target_column: "{TARGET_COLUMN}"'
            "\n  target_values: [0, 1]"
            '\n  model_name: "xgb_classifier"'
        )

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

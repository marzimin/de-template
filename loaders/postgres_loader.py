import os
import re
from typing import Any

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

log = structlog.get_logger()

IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
INVALID_IDENTIFIER_CHARS = re.compile(r"[^a-z0-9_]+")


def _engine_from_env() -> Engine:
    host = os.environ["POSTGRES_HOST"]
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("WAREHOUSE_USER") or os.environ["POSTGRES_USER"]
    password = os.environ.get("WAREHOUSE_PASSWORD") or os.environ["POSTGRES_PASSWORD"]
    db = os.environ.get("WAREHOUSE_DB") or os.environ["POSTGRES_DB"]
    url = URL.create(
        "postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=db,
    )
    return create_engine(url)


def _validate_identifier(identifier: str, kind: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"Invalid {kind} name {identifier!r}. Use lowercase letters, numbers, "
            "and underscores, starting with a letter or underscore."
        )
    return identifier


def _normalize_column_name(name: str) -> str:
    normalized = INVALID_IDENTIFIER_CHARS.sub("_", name.strip().lower()).strip("_")
    if not normalized:
        raise ValueError(f"Column name {name!r} cannot be normalized.")
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return _validate_identifier(normalized, "column")


def _normalize_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    source_columns = list(
        dict.fromkeys(column for record in records for column in record)
    )
    column_map = {column: _normalize_column_name(column) for column in source_columns}

    if len(set(column_map.values())) != len(column_map):
        raise ValueError(
            "Record contains column names that normalize to the same identifier."
        )

    normalized_records = [
        {column_map[column]: record.get(column) for column in source_columns}
        for record in records
    ]
    return normalized_records, list(column_map.values())


class PostgresLoader:
    """Loads records into a Postgres table in the raw schema.

    Usage:
        loader = PostgresLoader()
        loader.load(records, table="raw.example_items")
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or _engine_from_env()

    def load(self, records: list[dict[str, Any]], table: str) -> int:
        if not records:
            log.info("load_skipped", table=table, reason="empty records")
            return 0

        parts = table.split(".")
        if len(parts) > 2:
            raise ValueError("Table must be in 'table' or 'schema.table' format.")

        schema, tbl = parts if len(parts) == 2 else ("raw", parts[0])
        schema = _validate_identifier(schema, "schema")
        tbl = _validate_identifier(tbl, "table")
        normalized_records, columns = _normalize_records(records)
        col_list = ", ".join(columns)
        placeholders = ", ".join(f":{col}" for col in columns)

        with self.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {schema}.{tbl} "
                    f"({', '.join(f'{col} TEXT' for col in columns)})"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO {schema}.{tbl} ({col_list}) VALUES ({placeholders})"
                ),
                normalized_records,
            )

        log.info("load_complete", table=table, rows=len(records))
        return len(records)

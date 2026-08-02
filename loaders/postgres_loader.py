"""Load extracted records into the warehouse's raw schema."""

from typing import Any, Literal

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.warehouse import (
    DEFAULT_SCHEMA,
    engine_from_env,
    normalize_column_name,
    split_relation,
)

log = structlog.get_logger()

#: How a load treats rows already in the table.
#:
#:   ``append``   add to what is there. The default, and the right choice when
#:                the source is a growing log you fetch incrementally. Running
#:                the same pipeline twice loads the data twice, so deduplicate
#:                in the staging model — see dbt/models/staging/.
#:   ``replace``  empty the table first. For small sources you re-fetch in full
#:                every run, where a snapshot is simpler than a history.
LoadMode = Literal["append", "replace"]


def _normalize_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalise record keys to SQL identifiers and square up the column set.

    Records from an API are often ragged — a key present on one and absent on
    the next. Every record is widened to the union of all keys so a single
    multi-row INSERT works, with the missing values as NULL.

    Args:
        records: The raw records from an extractor.

    Returns:
        The normalised records and the ordered column names.

    Raises:
        ValueError: If two source columns normalise to the same identifier,
            which would silently drop one of them.
    """
    source_columns = list(
        dict.fromkeys(column for record in records for column in record)
    )
    column_map = {column: normalize_column_name(column) for column in source_columns}

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

    Every column is created as ``TEXT``. That is deliberate: the raw layer
    preserves what the source sent, and casting is a modelling decision that
    belongs in dbt's staging models where it is visible and testable, rather
    than being guessed at by the loader.

    Usage:
        loader = PostgresLoader()
        loader.load(records, table="raw.example_items")
    """

    def __init__(self, engine: Engine | None = None, mode: LoadMode = "append") -> None:
        """Configure the loader.

        Args:
            engine: Warehouse engine. Built from the environment when omitted.
            mode: See :data:`LoadMode`. Set it per source via ``load_mode`` in
                ``cfg/config.yaml`` rather than here.

        Raises:
            ValueError: If ``mode`` is not a supported load mode.
        """
        if mode not in ("append", "replace"):
            raise ValueError(
                f"Unsupported load mode {mode!r}. Use 'append' or 'replace'."
            )
        self.engine = engine or engine_from_env()
        self.mode: LoadMode = mode

    def load(
        self, records: list[dict[str, Any]], table: str, mode: LoadMode | None = None
    ) -> int:
        """Write records to a table, creating the schema and table if needed.

        Args:
            records: Records to insert. An empty list is a no-op — including in
                ``replace`` mode, where truncating on an empty extract would
                turn a transient API failure into data loss.
            table: Destination as ``schema.table``, or ``table`` to default to
                the raw schema.
            mode: Overrides the instance's mode for this call.

        Returns:
            The number of rows inserted.
        """
        if not records:
            log.info("load_skipped", table=table, reason="empty records")
            return 0

        effective_mode = mode or self.mode
        schema, tbl = split_relation(table, DEFAULT_SCHEMA)
        normalized_records, columns = _normalize_records(records)
        col_list = ", ".join(columns)
        placeholders = ", ".join(f":{col}" for col in columns)

        # One transaction, so a failed insert cannot leave the table truncated.
        with self.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {schema}.{tbl} "
                    f"({', '.join(f'{col} TEXT' for col in columns)})"
                )
            )
            if effective_mode == "replace":
                conn.execute(text(f"DELETE FROM {schema}.{tbl}"))
            conn.execute(
                text(
                    f"INSERT INTO {schema}.{tbl} ({col_list}) VALUES ({placeholders})"
                ),
                normalized_records,
            )

        log.info("load_complete", table=table, rows=len(records), mode=effective_mode)
        return len(records)

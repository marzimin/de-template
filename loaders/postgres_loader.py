import os
from typing import Any

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


def _engine_from_env() -> Engine:
    host = os.environ["POSTGRES_HOST"]
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}")


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

        schema, tbl = table.split(".") if "." in table else ("raw", table)
        columns = list(records[0].keys())
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
                records,
            )

        log.info("load_complete", table=table, rows=len(records))
        return len(records)

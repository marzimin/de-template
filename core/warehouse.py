"""Warehouse connection and SQL identifier handling.

Both the load and export layers talk to the same Postgres warehouse, so the
engine construction and the identifier validation live here rather than being
duplicated on either side.
"""

import os
import re

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
INVALID_IDENTIFIER_CHARS = re.compile(r"[^a-z0-9_]+")

DEFAULT_SCHEMA = "raw"


def engine_from_env() -> Engine:
    """Build a SQLAlchemy engine from the ``WAREHOUSE_*`` environment variables.

    ``POSTGRES_HOST`` and ``POSTGRES_PORT`` locate the server; the
    ``WAREHOUSE_*`` triple selects the database and the role that owns it. The
    same split is used by ``dbt/profiles.yml``, so both connect as the same user.

    Returns:
        A configured, unconnected engine.

    Raises:
        KeyError: If a required variable is unset.
    """
    host = os.environ["POSTGRES_HOST"]
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ["WAREHOUSE_USER"]
    password = os.environ["WAREHOUSE_PASSWORD"]
    database = os.environ["WAREHOUSE_DB"]
    url = URL.create(
        "postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
    )
    return create_engine(url)


def validate_identifier(identifier: str, kind: str) -> str:
    """Reject anything that is not a plain lowercase SQL identifier.

    Schema and table names are interpolated into DDL, where bind parameters are
    not available, so they are validated instead of escaped.

    Args:
        identifier: The candidate name.
        kind: What is being named, used in the error message.

    Returns:
        The identifier, unchanged.

    Raises:
        ValueError: If the identifier contains anything but lowercase letters,
            digits, and underscores, or does not start with a letter or
            underscore.
    """
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"Invalid {kind} name {identifier!r}. Use lowercase letters, numbers, "
            "and underscores, starting with a letter or underscore."
        )
    return identifier


def normalize_column_name(name: str) -> str:
    """Normalise a source column name to a lowercase SQL identifier.

    Note that ds-template-local normalises the *same* names to UPPER_SNAKE when
    it reads an exported file. Both are lossless round trips through the
    underscore form, so a column landing here as ``order_id`` arrives there as
    ``ORDER_ID``.

    Args:
        name: The raw column name from the source system.

    Returns:
        The normalised identifier.

    Raises:
        ValueError: If the name normalises to an empty string.
    """
    normalized = INVALID_IDENTIFIER_CHARS.sub("_", name.strip().lower()).strip("_")
    if not normalized:
        raise ValueError(f"Column name {name!r} cannot be normalized.")
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return validate_identifier(normalized, "column")


def split_relation(
    relation: str, default_schema: str = DEFAULT_SCHEMA
) -> tuple[str, str]:
    """Split a ``schema.table`` (or bare ``table``) reference into its parts.

    Args:
        relation: The relation reference.
        default_schema: Schema to assume when the reference has no qualifier.

    Returns:
        A validated ``(schema, table)`` pair.

    Raises:
        ValueError: If the reference has more than one qualifier, or either part
            is not a valid identifier.
    """
    parts = relation.split(".")
    if len(parts) > 2:
        raise ValueError("Table must be in 'table' or 'schema.table' format.")

    schema, table = parts if len(parts) == 2 else (default_schema, parts[0])
    return (
        validate_identifier(schema, "schema"),
        validate_identifier(table, "table"),
    )

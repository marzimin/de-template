import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@pytest.fixture
def pg_engine() -> Engine:
    """In-memory SQLite engine for unit tests that don't need a real Postgres."""
    return create_engine("sqlite:///:memory:")

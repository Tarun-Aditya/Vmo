import pytest
from sqlalchemy import text


@pytest.fixture(scope="session")
def db():
    """A real DB connection, or skip (unit tests above don't need one)."""
    from app.db import engine

    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
    except Exception:
        pytest.skip("database not reachable")
    return engine

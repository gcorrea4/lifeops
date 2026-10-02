"""Shared pytest fixtures for router tests.

Database strategy:
- SQLite in-memory via StaticPool so every connection in the process shares
  the same in-memory file (required for TestClient + fixture to see the same data).
- check_same_thread=False required for SQLite when used across threads (TestClient).
- PRAGMA foreign_keys = ON emitted on every new connection so ON DELETE CASCADE
  and FK integrity are actually enforced during tests.
- app.main.engine is patched to the test engine so the lifespan's create_all
  never touches the real MySQL instance.
- get_db is overridden via dependency_overrides so every request uses the
  same in-memory SQLite session.
- Tables are truncated between tests to ensure isolation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import Base, get_db
from app.main import app
from app.models import fixed_block, scheduled_slot, task  # noqa: F401 — ensure models registered

# ---------------------------------------------------------------------------
# Test engine — SQLite in-memory, shared pool, FK enforcement
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key enforcement on every SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch the real MySQL engine used by the lifespan's create_all — must happen
# before TestClient is constructed (which triggers the lifespan startup).
main_module.engine = test_engine

# Create all tables now against the test engine.
Base.metadata.create_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Dependency override — routes every request to the test session
# ---------------------------------------------------------------------------

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_all(db):
    """Delete all rows from every table (FK checks disabled temporarily)."""
    db.execute(text("PRAGMA foreign_keys=OFF"))
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.execute(text("PRAGMA foreign_keys=ON"))
    db.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """Yields a database session backed by the in-memory SQLite engine.

    Truncates all tables after each test to ensure isolation.
    """
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        _truncate_all(db)
        db.close()


@pytest.fixture()
def client(db_session):
    """Yields a TestClient wired to the in-memory SQLite database.

    Depends on db_session so the same truncation lifecycle applies.
    """
    with TestClient(app) as c:
        yield c

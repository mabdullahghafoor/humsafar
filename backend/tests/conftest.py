"""
Test fixtures.

These tests need a PostgreSQL database of their OWN. They never touch your
development database. Point TEST_DATABASE_URL at an empty database whose name
contains "test", for example:

    createdb -U postgres humsafar_test
    set TEST_DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/humsafar_test   (Windows cmd)
    $env:TEST_DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@localhost:5432/humsafar_test"  (PowerShell)

If TEST_DATABASE_URL is not set, the database tests are skipped, not failed.
"""

import os

# The background scheduler must never run during tests (tests call the jobs directly).
os.environ.setdefault("SCHEDULER_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set; skipping database tests.")
    if TEST_DATABASE_URL == get_settings().DATABASE_URL:
        pytest.fail("TEST_DATABASE_URL must not be the same as your development DATABASE_URL.")
    if "test" not in (make_url(TEST_DATABASE_URL).database or "").lower():
        pytest.fail("Safety check: the test database name must contain 'test'.")

    eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    import app.models  # noqa: F401  (register all tables)

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        # Clean slate for the next test.
        with engine.begin() as conn:
            names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            conn.execute(text(f"TRUNCATE TABLE {names} CASCADE"))


@pytest.fixture()
def client(engine, db):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

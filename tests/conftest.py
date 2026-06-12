"""DB fixtures for the durable-jobs tests (#5).

These tests run against REAL Postgres — faking lease/idempotency semantics in
dicts would prove nothing (the failure tests shape the job model, arch §5.2).
If Postgres is unreachable the fixture FAILS LOUD with the fix; it never skips.

    docker compose up -d db

NOTE: isolation is per-test TRUNCATE on one shared database — sequential only.
Parallel runners (pytest-xdist) would need a per-worker database name.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg import sql

from flowops.actuators.dummy import DummyActuator
from flowops.config import Settings
from flowops.db import create_pool
from flowops.db.migrate import run_migrations
from flowops.models.enums import Profile
from flowops.services import SandboxService
from flowops.store import Store

TEST_DB_URL = os.environ.get(
    "FLOWOPS_TEST_DATABASE_URL", "postgresql://flowops:flowops@localhost:5432/flowops_test"
)
_HINT = "Postgres is required for the jobs-table tests — run: docker compose up -d db"


class CountingActuator(DummyActuator):
    """DummyActuator with call counters — proves no-double-apply and that
    status reads never hit the actuator."""

    def __init__(self) -> None:
        self.plan_calls = 0
        self.apply_calls = 0
        self.destroy_calls = 0
        self.status_calls = 0

    def plan(self, intent):
        self.plan_calls += 1
        return super().plan(intent)

    def apply(self, intent):
        self.apply_calls += 1
        return super().apply(intent)

    def destroy(self, handle):
        self.destroy_calls += 1
        return super().destroy(handle)

    def status(self, handle):
        self.status_calls += 1
        return super().status(handle)


def _ensure_test_db() -> None:
    try:
        with psycopg.connect(TEST_DB_URL, connect_timeout=3):
            return
    except psycopg.OperationalError as exc:
        if "does not exist" not in str(exc):
            pytest.fail(f"{_HINT}\n(cannot reach {TEST_DB_URL}: {exc})", pytrace=False)
    # Server is up but the test database is missing — create it via whichever
    # maintenance database exists (compose ships 'flowops'; stock images 'postgres').
    base, _, dbname = TEST_DB_URL.rpartition("/")
    last_exc: Exception | None = None
    for maintenance_db in ("flowops", "postgres"):
        try:
            with psycopg.connect(
                f"{base}/{maintenance_db}", autocommit=True, connect_timeout=3
            ) as conn:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            return
        except psycopg.OperationalError as exc:
            last_exc = exc
    pytest.fail(f"{_HINT}\n(cannot create {dbname}: {last_exc})", pytrace=False)


@pytest.fixture(scope="session")
def db_pool():
    _ensure_test_db()
    run_migrations(TEST_DB_URL)
    pool = create_pool(TEST_DB_URL)
    yield pool
    pool.close()


@pytest.fixture
def store(db_pool):
    with db_pool.connection() as conn:
        conn.execute(
            "TRUNCATE gate_records, tasks, work_requests, blueprints RESTART IDENTITY CASCADE"
        )
    s = Store(db_pool)
    s.seed_dev_blueprint()
    return s


@pytest.fixture
def actuator():
    return CountingActuator()


@pytest.fixture
def dev_settings():
    return Settings(profile=Profile.DEV, region="us-east-1", database_url=TEST_DB_URL)


@pytest.fixture
def service(dev_settings, store, actuator):
    return SandboxService(dev_settings, store=store, actuator=actuator)

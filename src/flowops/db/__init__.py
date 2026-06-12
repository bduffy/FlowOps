"""Postgres connection pool for the control plane (#5)."""

from __future__ import annotations

from psycopg_pool import ConnectionPool


def create_pool(database_url: str) -> ConnectionPool:
    pool = ConnectionPool(database_url, min_size=1, max_size=10, open=False)
    pool.open(wait=True, timeout=30)
    return pool

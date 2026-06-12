"""Versioned SQL migrations, no framework.

Files in db/migrations/ named NNNN_description.sql run in order, exactly once,
recorded in schema_migrations. A pg_advisory_lock serialises concurrent runners
(API replicas all migrate at startup). Run standalone: python -m flowops.db.migrate
"""

from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_ADVISORY_LOCK_KEY = 727_150  # arbitrary app-wide constant: "FlowOps migrations"


def _ordered_migrations() -> list[tuple[int, Path]]:
    """Migrations ordered by parsed version (not filename sort, which mis-orders
    unpadded numbers). Malformed names and duplicate versions fail loud up front,
    before any SQL runs."""
    seen: dict[int, Path] = {}
    for path in MIGRATIONS_DIR.glob("*.sql"):
        prefix = path.name.split("_", 1)[0]
        if not prefix.isdigit():
            raise RuntimeError(f"migration filename must start with NNNN_: {path.name}")
        version = int(prefix)
        if version in seen:
            raise RuntimeError(
                f"duplicate migration version {version}: {seen[version].name} and {path.name}"
            )
        seen[version] = path
    return sorted(seen.items())


def run_migrations(database_url: str) -> list[int]:
    """Apply pending migrations; return the versions applied this run."""
    applied: list[int] = []
    migrations = _ordered_migrations()
    with psycopg.connect(database_url, connect_timeout=10) as conn, conn.cursor() as cur:
        # Bounded waits: a wedged migrator on another replica must surface as a
        # startup error, never an indefinite silent hang.
        cur.execute("SET lock_timeout = '60s'")
        cur.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,))
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.commit()
        cur.execute("SELECT version FROM schema_migrations")
        done = {version for (version,) in cur.fetchall()}
        for version, path in migrations:
            if version in done:
                continue
            # The migration and its bookkeeping row commit atomically.
            cur.execute(path.read_text())
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            conn.commit()
            applied.append(version)
        # advisory lock released with the connection
    return applied


def main() -> None:
    from ..config import load_settings

    applied = run_migrations(load_settings().database_url)
    print(f"migrations applied: {applied if applied else 'none (schema up to date)'}")


if __name__ == "__main__":
    main()

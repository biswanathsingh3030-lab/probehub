"""PostgreSQL storage for probe data."""

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS probe_data (
    id           BIGSERIAL PRIMARY KEY,
    probe_id     TEXT        NOT NULL,
    category     TEXT        NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload      JSONB       NOT NULL
);
-- Migration for tables created before `category` existed (old rows were system metrics).
ALTER TABLE probe_data ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'system';
ALTER TABLE probe_data ALTER COLUMN category DROP DEFAULT;
CREATE INDEX IF NOT EXISTS probe_data_probe_time_idx
    ON probe_data (probe_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS probe_data_category_time_idx
    ON probe_data (category, collected_at DESC);
"""


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool(database_url, min_size=1, max_size=10, open=False)

    def open(self) -> None:
        self._pool.open(wait=True, timeout=10)
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> bool:
        try:
            with self._pool.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def insert(
        self, probe_id: str, category: str, collected_at: datetime, data: dict[str, Any]
    ) -> tuple[int, datetime]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO probe_data (probe_id, category, collected_at, payload) "
                "VALUES (%s, %s, %s, %s) RETURNING id, received_at",
                (probe_id, category, collected_at, Jsonb(data)),
            ).fetchone()
        return row[0], row[1]

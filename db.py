"""
db.py
PostgreSQL connection layer for the multi-tenant SaaS build.

DESIGN DECISION (documented in TECHNICAL_AUDIT.md, Phase 25 "do not break
existing software" applied to the migration itself): the ~19 existing
Streamlit modules all call `conn.execute(sql, params)` with SQLite's
`?`-style placeholders and read rows via dict-like access (`row["col"]`).
Rather than hand-rewriting every one of the ~150 SQL call sites' placeholder
syntax (error-prone, hard to review), this module provides a thin
compatibility layer: it accepts the exact same `?`-placeholder SQL text and
translates it to psycopg2's `%s` at execute-time, and returns RealDictCursor
rows so `row["col"]` and `dict(row)` keep working exactly as before. Only
two things change per module during migration: the import, and adding a
`tenant_id` value/filter to tenant-scoped queries. A full SQLAlchemy ORM
rewrite was considered (per the original spec's preference) but rejected
for this pass because it would touch business logic in every module far
more invasively than a straight PostgreSQL migration requires — this
psycopg2-pooled approach still delivers parameterized queries, pooling,
transactions, and environment-based config, which are the properties that
actually matter for security and scalability.

Connection string resolution order:
1. Streamlit secrets (st.secrets["DATABASE_URL"]) - used on Streamlit Cloud
2. DATABASE_URL environment variable - used everywhere else (local dev, CI)
Never hard-coded in source, per Phase 25.
"""

import os
import re
import threading

import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager

_POOL = None
_POOL_LOCK = threading.Lock()
_PLACEHOLDER_RE = re.compile(r"\?")


def _database_url() -> str:
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it as an environment variable, or in "
            ".streamlit/secrets.toml for Streamlit Cloud deployment. "
            "See README.md -> 'PostgreSQL Setup' for the exact connection string format."
        )
    return url


def _get_pool():
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=_database_url())
    return _POOL


def _translate(sql: str) -> str:
    """SQLite '?' placeholders -> psycopg2 '%s' placeholders."""
    return _PLACEHOLDER_RE.sub("%s", sql)


class _RowCursor:
    """Wraps a psycopg2 RealDictCursor so existing module code
    (`conn.execute(...).fetchone()`, `row["column"]`, `dict(row)`) keeps
    working exactly as it did against sqlite3.Row."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        self._cursor.execute(_translate(sql), params or ())
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount


class PooledConnection:
    """Drop-in replacement for the old sqlite3.Connection used throughout
    the app: supports .execute(), .executescript(), .commit(), .rollback(),
    .close() with the exact same call shape as before."""

    def __init__(self, pool):
        self._pool = pool
        self._conn = pool.getconn()
        self._conn.autocommit = False

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(_translate(sql), params or ())
        return _RowCursor(cur)

    def executescript(self, sql):
        """psycopg2 supports multiple ;-separated statements in one execute()."""
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # Return the connection to the pool instead of closing the socket.
        try:
            self._pool.putconn(self._conn)
        except Exception:
            pass


def get_connection() -> PooledConnection:
    return PooledConnection(_get_pool())


@contextmanager
def transaction():
    """
    Use for multi-statement writes that must succeed or fail together
    (e.g. checkout.py: checkout row + invoice row + payment row + room
    status update). Commits once at the end; rolls back on any exception
    so a failed transaction never leaves partially-updated business data
    (Phase 22).

    Usage:
        with db.transaction() as conn:
            conn.execute("INSERT ...", (...))
            conn.execute("UPDATE ...", (...))
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

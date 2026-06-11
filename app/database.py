import sqlite3
import click
from flask import current_app, g

import config


def is_postgres():
    """True if the app is configured to use Postgres (DATABASE_URL set)."""
    return bool(config.DATABASE_URL)


class _PgRow(tuple):
    """A tuple subclass that also supports dict-style access by column name,
    mimicking sqlite3.Row so existing route code (row['col'], row[0],
    dict(row)) keeps working unchanged against psycopg2."""

    def __new__(cls, values, colnames):
        obj = super().__new__(cls, values)
        obj._colnames = colnames
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                idx = self._colnames.index(key)
            except ValueError:
                raise KeyError(key)
            return tuple.__getitem__(self, idx)
        return tuple.__getitem__(self, key)

    def keys(self):
        return self._colnames


class _PgCursorWrapper:
    """Wraps a psycopg2 cursor so fetchone()/fetchall() return _PgRow
    objects (dict + index access), matching sqlite3.Row behavior."""

    def __init__(self, cursor):
        self._cursor = cursor

    def _colnames(self):
        return [d[0] for d in self._cursor.description] if self._cursor.description else []

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return _PgRow(row, self._colnames())

    def fetchall(self):
        cols = self._colnames()
        return [_PgRow(r, cols) for r in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        cols = self._colnames()
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [_PgRow(r, cols) for r in rows]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        # psycopg2 cursors don't support lastrowid. Call sites that need the
        # generated PK must use "RETURNING <pk_column>" and fetchone() instead.
        return None

    def __iter__(self):
        cols = self._colnames()
        for r in self._cursor:
            yield _PgRow(r, cols)

    def close(self):
        self._cursor.close()


class _PgWrapper:
    """Wraps a psycopg2 connection to provide the small subset of the
    sqlite3.Connection API used throughout routes/: execute, executemany,
    commit, close."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return _PgCursorWrapper(cur)

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(sql, seq_of_params)
        return _PgCursorWrapper(cur)

    def executescript(self, sql_script):
        cur = self._conn.cursor()
        cur.execute(sql_script)
        return _PgCursorWrapper(cur)

    def cursor(self):
        return _PgCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    """Open a database connection for the current request, reusing if already open."""
    if 'db' not in g:
        if is_postgres():
            import psycopg2
            conn = psycopg2.connect(config.DATABASE_URL)
            g.db = _PgWrapper(conn)
        else:
            g.db = sqlite3.connect(
                current_app.config['DATABASE'],
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            g.db.row_factory = sqlite3.Row  # rows behave like dicts
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)


def table_exists(db, name):
    """Dialect-aware check for whether a table exists."""
    if is_postgres():
        row = db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (name,)
        ).fetchone()
    else:
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,)
        ).fetchone()
    return row is not None

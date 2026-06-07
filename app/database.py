import sqlite3
import click
from flask import current_app, g


def get_db():
    """Open a database connection for the current request, reusing if already open."""
    if 'db' not in g:
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

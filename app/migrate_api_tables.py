"""
Migration: Create course_api_cache and api_request_log tables.

Run from app/ with DATABASE_URL set:
    DATABASE_URL=<your-supabase-url> python migrate_api_tables.py

Or run the SQL directly in the Supabase SQL Editor.
"""
import os
import sys


DDL = """
CREATE TABLE IF NOT EXISTS course_api_cache (
    api_course_id  INTEGER PRIMARY KEY,
    response_json  TEXT    NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_request_log (
    log_id        SERIAL PRIMARY KEY,
    endpoint      TEXT    NOT NULL,
    league_id     INTEGER,
    user_id       INTEGER,
    response_code INTEGER,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_request_log_month
    ON api_request_log (DATE_TRUNC('month', requested_at));
"""


def run():
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    print("Migration complete: course_api_cache and api_request_log tables ready.")
    conn.close()


if __name__ == '__main__':
    run()

"""
Migration: create player_nicknames table for iOS OCR name matching.

Run from app/ with DATABASE_URL set:
    DATABASE_URL=<your-supabase-url> python migrate_player_nicknames.py

Or run directly in the Supabase SQL Editor:
    CREATE TABLE IF NOT EXISTS player_nicknames (
        nickname_id SERIAL PRIMARY KEY,
        player_id   INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
        nickname    TEXT    NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS player_nicknames_pid_lower_idx
        ON player_nicknames (player_id, lower(nickname));
"""
import os
import sys


def run():
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'player_nicknames'
    """)
    if cur.fetchone():
        print("player_nicknames table already exists — nothing to do.")
    else:
        cur.execute("""
            CREATE TABLE player_nicknames (
                nickname_id SERIAL PRIMARY KEY,
                player_id   INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
                nickname    TEXT    NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX player_nicknames_pid_lower_idx
                ON player_nicknames (player_id, lower(nickname))
        """)
        conn.commit()
        print("Created player_nicknames table.")

    cur.close()
    conn.close()


if __name__ == '__main__':
    run()

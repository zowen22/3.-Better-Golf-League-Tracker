"""
Migration: add scoring_mode column to league_settings.

Run from app/ with DATABASE_URL set:
    DATABASE_URL=<your-supabase-url> python migrate_scoring_mode.py

Or run this SQL directly in the Supabase SQL Editor:
    ALTER TABLE league_settings
    ADD COLUMN IF NOT EXISTS scoring_mode TEXT NOT NULL DEFAULT 'match_play';
"""
import os
import sys

def run():
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        print("ERROR: DATABASE_URL not set. Set it before running this migration.", file=sys.stderr)
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'league_settings'
          AND column_name  = 'scoring_mode'
    """)
    if cur.fetchone():
        print("scoring_mode already exists — nothing to do.")
    else:
        cur.execute(
            "ALTER TABLE league_settings ADD COLUMN scoring_mode TEXT NOT NULL DEFAULT 'match_play'"
        )
        conn.commit()
        print("Added scoring_mode column to league_settings.")

    cur.close()
    conn.close()

if __name__ == '__main__':
    run()

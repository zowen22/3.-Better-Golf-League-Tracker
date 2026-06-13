"""
Migration: add UNIQUE constraint on rounds(matchup_id).

Run from app/ with DATABASE_URL set:
    DATABASE_URL=<your-supabase-url> python migrate_rounds_unique.py

Or run directly in the Supabase SQL Editor:
    ALTER TABLE rounds ADD CONSTRAINT rounds_matchup_id_unique UNIQUE (matchup_id);
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
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name   = 'rounds'
          AND constraint_type = 'UNIQUE'
          AND constraint_name = 'rounds_matchup_id_unique'
    """)
    if cur.fetchone():
        print("rounds_matchup_id_unique already exists — nothing to do.")
    else:
        cur.execute(
            "ALTER TABLE rounds ADD CONSTRAINT rounds_matchup_id_unique UNIQUE (matchup_id)"
        )
        conn.commit()
        print("Added UNIQUE(matchup_id) constraint to rounds.")

    cur.close()
    conn.close()


if __name__ == '__main__':
    run()

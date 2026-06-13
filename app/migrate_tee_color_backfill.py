"""
Migration: backfill tee_color = tee_name where tee_color is NULL.

Run from app/ with DATABASE_URL set:
    DATABASE_URL=<your-supabase-url> python migrate_tee_color_backfill.py

Or run directly in the Supabase SQL Editor:
    UPDATE tees SET tee_color = tee_name WHERE tee_color IS NULL;
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

    cur.execute("SELECT COUNT(*) FROM tees WHERE tee_color IS NULL")
    count = cur.fetchone()[0]

    if count == 0:
        print("No tees with NULL tee_color — nothing to do.")
    else:
        cur.execute("UPDATE tees SET tee_color = tee_name WHERE tee_color IS NULL")
        conn.commit()
        print(f"Backfilled tee_color = tee_name for {count} tee row(s).")

    cur.close()
    conn.close()


if __name__ == '__main__':
    run()

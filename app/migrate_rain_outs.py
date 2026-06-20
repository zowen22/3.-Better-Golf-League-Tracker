"""Migration: add rain out / makeup columns to matchups."""
import os, psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur  = conn.cursor()
cur.execute("""
    ALTER TABLE matchups
        ADD COLUMN IF NOT EXISTS week_label       TEXT    DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS makeup_for_week  INTEGER DEFAULT NULL;
""")
conn.commit()
cur.close()
conn.close()
print("Done: week_label + makeup_for_week added to matchups.")

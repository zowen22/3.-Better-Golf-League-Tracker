"""Migration: add multi_course column to league_settings."""
import os, psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur  = conn.cursor()

cur.execute("""
    ALTER TABLE league_settings
    ADD COLUMN IF NOT EXISTS multi_course INTEGER NOT NULL DEFAULT 0
""")

conn.commit()
cur.close()
conn.close()
print("Done: multi_course column added to league_settings.")

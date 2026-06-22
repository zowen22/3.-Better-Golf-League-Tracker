"""
Migration: add trigger_round_id and manual-override columns to handicap_history.

Run once against the production database.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    sys.exit('DATABASE_URL not set')

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
cur = conn.cursor()

ALTERS = [
    "ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS trigger_round_id INTEGER REFERENCES rounds(round_id)",
    "ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS is_manual_override INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS override_reason TEXT",
    "ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS override_by_user_id INTEGER",
    "ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS override_at TEXT",
]

for sql in ALTERS:
    print(f"  {sql[:80]}…")
    cur.execute(sql)

conn.commit()
cur.close()
conn.close()
print("Done.")

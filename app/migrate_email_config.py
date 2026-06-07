"""
Migration: Add email / SMTP configuration columns to leagues table.
Run once: python migrate_email_config.py
"""

import sqlite3, os, shutil, sys

DB_SRC = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_SRC = os.path.abspath(DB_SRC)
DB_TMP = '/sessions/wizardly-beautiful-mendel/tmp/golf_migrate_email.db'

print(f"Source DB: {DB_SRC}")
shutil.copy2(DB_SRC, DB_TMP)

conn = sqlite3.connect(DB_TMP)
cur  = conn.cursor()

# Check existing columns
cur.execute("PRAGMA table_info(leagues)")
existing = {row[1] for row in cur.fetchall()}

COLUMNS = [
    ("email_enabled",          "INTEGER DEFAULT 0"),
    ("smtp_host",              "TEXT DEFAULT NULL"),
    ("smtp_port",              "INTEGER DEFAULT 587"),
    ("smtp_user",              "TEXT DEFAULT NULL"),
    ("smtp_password",          "TEXT DEFAULT NULL"),
    ("smtp_from_email",        "TEXT DEFAULT NULL"),
    ("smtp_from_name",         "TEXT DEFAULT NULL"),
    ("smtp_use_tls",           "INTEGER DEFAULT 1"),
    ("email_on_announcement",  "INTEGER DEFAULT 1"),
    ("email_on_round_posted",  "INTEGER DEFAULT 1"),
    ("email_on_sub_assigned",  "INTEGER DEFAULT 0"),
]

added = []
for col, defn in COLUMNS:
    if col not in existing:
        cur.execute(f"ALTER TABLE leagues ADD COLUMN {col} {defn}")
        added.append(col)
        print(f"  Added column: {col}")
    else:
        print(f"  Already exists: {col}")

conn.commit()
conn.close()

shutil.copy2(DB_TMP, DB_SRC)
os.remove(DB_TMP)
print(f"\nDone. Columns added: {added or 'none (already up to date)'}")

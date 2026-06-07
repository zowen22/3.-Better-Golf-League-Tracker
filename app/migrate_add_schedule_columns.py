"""
Migration: add tee_time, starting_hole, week_type to matchups.
Run once from D:\GolfLeague\app\  →  python migrate_add_schedule_columns.py
"""
import sqlite3, shutil, os

SRC = r"D:\GolfLeague\Database\golf_league.db"
TMP = r"C:\Windows\Temp\golf_league_sched_mig.db"

shutil.copy2(SRC, TMP)
conn = sqlite3.connect(TMP)
cur  = conn.cursor()

cur.execute("PRAGMA table_info(matchups)")
existing = {row[1] for row in cur.fetchall()}

for col, defn in [
    ('tee_time',      'TEXT'),
    ('starting_hole', 'INTEGER NOT NULL DEFAULT 1'),
    ('week_type',     "TEXT NOT NULL DEFAULT 'Normal'"),
]:
    if col not in existing:
        cur.execute(f"ALTER TABLE matchups ADD COLUMN {col} {defn}")
        print(f"Added {col}")
    else:
        print(f"{col} already exists — skipped")

conn.commit()
conn.close()
shutil.copy2(TMP, SRC)
os.remove(TMP)
print("Migration complete.")

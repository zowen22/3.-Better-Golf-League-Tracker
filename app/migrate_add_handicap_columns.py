"""
Migration: add padding_score_count and low_scores_to_drop to league_settings.
Run once from D:\GolfLeague\app\  →  python migrate_add_handicap_columns.py
"""
import sqlite3, shutil, os

SRC = r"D:\GolfLeague\Database\golf_league.db"
TMP = r"C:\Windows\Temp\golf_league_hcp_mig.db"

shutil.copy2(SRC, TMP)

conn = sqlite3.connect(TMP)
cur  = conn.cursor()

# Check which columns already exist
cur.execute("PRAGMA table_info(league_settings)")
existing = {row[1] for row in cur.fetchall()}

if 'padding_score_count' not in existing:
    cur.execute("ALTER TABLE league_settings ADD COLUMN padding_score_count INTEGER NOT NULL DEFAULT 0")
    print("Added padding_score_count")
else:
    print("padding_score_count already exists — skipped")

if 'low_scores_to_drop' not in existing:
    cur.execute("ALTER TABLE league_settings ADD COLUMN low_scores_to_drop INTEGER NOT NULL DEFAULT 0")
    print("Added low_scores_to_drop")
else:
    print("low_scores_to_drop already exists — skipped")

conn.commit()
conn.close()

shutil.copy2(TMP, SRC)
os.remove(TMP)
print("Migration complete.")

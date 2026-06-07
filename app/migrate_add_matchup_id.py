"""
Migration: add matchup_id column to player_absences if not already present.
Run once: python3 migrate_add_matchup_id.py
"""
import sqlite3, os, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, '..', 'Database', 'golf_league.db')

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute("PRAGMA table_info(player_absences)")
cols = [r[1] for r in cur.fetchall()]
print("Current columns:", cols)

if 'matchup_id' not in cols:
    print("Adding matchup_id column...")
    cur.execute("ALTER TABLE player_absences ADD COLUMN matchup_id INTEGER REFERENCES matchups(matchup_id)")
    conn.commit()
    print("Done.")
else:
    print("matchup_id already exists — nothing to do.")

cur.execute("PRAGMA table_info(player_absences)")
print("Updated columns:", [r[1] for r in cur.fetchall()])
conn.close()

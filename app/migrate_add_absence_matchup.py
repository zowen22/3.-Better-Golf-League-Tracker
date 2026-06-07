"""
Migration: add matchup_id column to player_absences.
This allows sub assignments to be stored before a round is created.
Run once from D:\GolfLeague\app\:  python migrate_add_absence_matchup.py
"""
import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_PATH = os.path.abspath(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Check if column already exists
cur.execute("PRAGMA table_info(player_absences)")
cols = [r[1] for r in cur.fetchall()]

if 'matchup_id' not in cols:
    cur.execute("ALTER TABLE player_absences ADD COLUMN matchup_id INTEGER REFERENCES matchups(matchup_id)")
    conn.commit()
    print("✅  Added matchup_id column to player_absences.")
else:
    print("ℹ️   matchup_id already exists — nothing to do.")

conn.close()

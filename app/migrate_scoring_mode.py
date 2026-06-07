"""
Migration: add scoring_mode column to league_settings.
Run once: python migrate_scoring_mode.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(league_settings)").fetchall()]
    if 'scoring_mode' not in cols:
        cur.execute("ALTER TABLE league_settings ADD COLUMN scoring_mode TEXT NOT NULL DEFAULT 'match_play'")
        conn.commit()
        print("Added scoring_mode column.")
    else:
        print("scoring_mode already exists — nothing to do.")
    conn.close()

if __name__ == '__main__':
    run()

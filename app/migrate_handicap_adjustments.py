"""
Migration: Create handicap_adjustments table.

Run once:  cd D:\GolfLeague\app && python migrate_handicap_adjustments.py

Stores per-player committee handicap adjustments (strokes added or subtracted by
the league administrator). One active adjustment per player per league; replacing
it simply updates the existing row.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

DDL = """
CREATE TABLE IF NOT EXISTS handicap_adjustments (
    adj_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         INTEGER NOT NULL,
    league_id         INTEGER NOT NULL,
    adjustment        REAL    NOT NULL DEFAULT 0,
    reason            TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    created_by_user_id INTEGER,
    UNIQUE (player_id, league_id)
);
"""

def run():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    print("Migration complete: handicap_adjustments table ready.")
    conn.close()

if __name__ == '__main__':
    run()

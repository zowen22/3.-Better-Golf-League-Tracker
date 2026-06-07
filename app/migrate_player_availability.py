"""
Migration: player_availability table
Run: cd D:\GolfLeague\app && python migrate_player_availability.py
"""
import sqlite3, sys, os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def run():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS player_availability (
            avail_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id   INTEGER NOT NULL,
            league_id   INTEGER NOT NULL,
            season_id   INTEGER NOT NULL,
            week_number INTEGER NOT NULL,
            available   INTEGER NOT NULL DEFAULT 1,
            note        TEXT,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(player_id, league_id, season_id, week_number)
        )
    """)
    db.commit()
    db.close()
    print("Migration complete: player_availability table created.")

if __name__ == '__main__':
    run()

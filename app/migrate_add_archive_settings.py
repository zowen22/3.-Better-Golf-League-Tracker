"""
Migration: Create archive_settings table for the Archive UI feature.

Run from D:\GolfLeague\app\:
    python migrate_add_archive_settings.py

This table stores per-season visibility and lock state for the archive feature.
Admins can archive past seasons and control whether members can view them.

Columns:
  archive_id            -- PK
  league_id             -- FK to leagues
  season_id             -- FK to seasons
  visible_to_members    -- 1 = shown in member archive view, 0 = hidden
  locked                -- 1 = score editing locked for this season
  unlocked_by_user_id   -- user who last unlocked (audit trail)
  unlock_date           -- ISO date when last unlocked
  unlock_reason         -- optional free-text reason
"""
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Check if table already exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='archive_settings'"
    )
    if cur.fetchone():
        print("archive_settings table already exists — nothing to do.")
        conn.close()
        return

    cur.executescript("""
        CREATE TABLE archive_settings (
            archive_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id             INTEGER NOT NULL,
            season_id             INTEGER NOT NULL,
            visible_to_members    INTEGER NOT NULL DEFAULT 1,
            locked                INTEGER NOT NULL DEFAULT 1,
            unlocked_by_user_id   INTEGER,
            unlock_date           TEXT,
            unlock_reason         TEXT,
            FOREIGN KEY (league_id)           REFERENCES leagues(league_id),
            FOREIGN KEY (season_id)           REFERENCES seasons(season_id),
            FOREIGN KEY (unlocked_by_user_id) REFERENCES users(user_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_archive_league_season
            ON archive_settings (league_id, season_id);
    """)

    conn.commit()
    print("Migration complete. Created archive_settings table.")
    conn.close()


if __name__ == '__main__':
    run()

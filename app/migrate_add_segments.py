"""
Migration: Add segment_start_week / segment_end_week to league_settings.

Run from D:\GolfLeague\app\:
    python migrate_add_segments.py

These columns power the Indiv / Segment / Season pts breakdown on Team Scorecards.
"""
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("PRAGMA table_info(league_settings)")
    existing_cols = {row[1] for row in cur.fetchall()}

    added = []
    if 'segment_start_week' not in existing_cols:
        cur.execute("ALTER TABLE league_settings ADD COLUMN segment_start_week INTEGER DEFAULT NULL")
        added.append('segment_start_week')

    if 'segment_end_week' not in existing_cols:
        cur.execute("ALTER TABLE league_settings ADD COLUMN segment_end_week INTEGER DEFAULT NULL")
        added.append('segment_end_week')

    if added:
        conn.commit()
        print(f"Migration complete. Added columns: {', '.join(added)}")
    else:
        print("Columns already exist — nothing to do.")

    conn.close()

if __name__ == '__main__':
    run()

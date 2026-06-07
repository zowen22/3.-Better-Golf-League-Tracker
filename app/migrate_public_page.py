"""
Migration: Add public_enabled and public_slug to leagues table.
Run: cd D:\GolfLeague\app && python migrate_public_page.py
"""
import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def migrate():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(leagues)").fetchall()]
    added = []
    if 'public_enabled' not in cols:
        cur.execute("ALTER TABLE leagues ADD COLUMN public_enabled INTEGER DEFAULT 0")
        added.append('public_enabled')
    if 'public_slug' not in cols:
        cur.execute("ALTER TABLE leagues ADD COLUMN public_slug TEXT DEFAULT NULL")
        added.append('public_slug')
    db.commit()
    db.close()
    if added:
        print(f"Added columns: {', '.join(added)}")
    else:
        print("Already up to date.")

if __name__ == '__main__':
    migrate()

"""
Migration: add api_key column to leagues table.
Run once: cd D:\GolfLeague\app && python migrate_api_key.py
"""
import os, sys, sqlite3, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(leagues)").fetchall()]
    if 'api_key' not in cols:
        conn.execute("ALTER TABLE leagues ADD COLUMN api_key TEXT DEFAULT NULL")
        conn.commit()
        print("Added api_key column to leagues.")
    else:
        print("api_key column already exists — nothing to do.")
    conn.close()

if __name__ == '__main__':
    run()

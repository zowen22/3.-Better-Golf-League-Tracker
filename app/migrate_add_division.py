"""
Migration: Add division_name column to teams table.
Run once from D:\GolfLeague\app\ with: python migrate_add_division.py
"""
import sqlite3, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, '..', 'Database', 'golf_league.db')

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Check if column already exists
cur.execute("PRAGMA table_info(teams)")
cols = [row[1] for row in cur.fetchall()]

if 'division_name' not in cols:
    cur.execute("ALTER TABLE teams ADD COLUMN division_name TEXT DEFAULT NULL")
    conn.commit()
    print("✅ Added division_name column to teams table.")
else:
    print("ℹ️  division_name column already exists — no change needed.")

conn.close()

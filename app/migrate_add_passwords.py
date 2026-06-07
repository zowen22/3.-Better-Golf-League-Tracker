"""
One-time migration: adds admin_password_hash and member_password_hash to leagues table.
Run once from D:\GolfLeague\app\ with: python migrate_add_passwords.py
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, '..', 'Database', 'golf_league.db')

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check if columns already exist
cur.execute("PRAGMA table_info(leagues)")
columns = [row[1] for row in cur.fetchall()]

added = []
if 'admin_password_hash' not in columns:
    cur.execute("ALTER TABLE leagues ADD COLUMN admin_password_hash TEXT")
    added.append('admin_password_hash')
if 'member_password_hash' not in columns:
    cur.execute("ALTER TABLE leagues ADD COLUMN member_password_hash TEXT")
    added.append('member_password_hash')

conn.commit()
conn.close()

if added:
    print(f"✅ Added columns: {', '.join(added)}")
else:
    print("✅ Columns already exist, nothing to do.")

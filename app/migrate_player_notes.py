"""
Migration: add notes column to players table.
Run once: cd D:\GolfLeague\app && python migrate_player_notes.py
"""
import sqlite3, shutil, os

DB_SRC  = r'D:\GolfLeague\Database\golf_league.db'
DB_TMP  = r'/tmp/golf_league_pnotes.db'

shutil.copy2(DB_SRC, DB_TMP)
con = sqlite3.connect(DB_TMP)
cur = con.cursor()

cols = [row[1] for row in cur.execute("PRAGMA table_info(players)").fetchall()]
if 'notes' not in cols:
    cur.execute("ALTER TABLE players ADD COLUMN notes TEXT DEFAULT NULL")
    con.commit()
    print("Added 'notes' column to players.")
else:
    print("'notes' column already exists — nothing to do.")

con.close()
shutil.copy2(DB_TMP, DB_SRC)
print("Done.")

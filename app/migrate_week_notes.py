"""
Migration: create week_notes table
Run once: cd D:\GolfLeague\app && python migrate_week_notes.py
"""
import sqlite3, os, shutil, time

DB_SRC = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_SRC = os.path.abspath(DB_SRC)
BACKUP = DB_SRC + f'.bak_weeknotes_{int(time.time())}'

shutil.copy2(DB_SRC, BACKUP)
print(f'Backup: {BACKUP}')

con = sqlite3.connect(DB_SRC)
cur = con.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS week_notes (
        note_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        league_id   INTEGER NOT NULL,
        season_id   INTEGER NOT NULL,
        week_number INTEGER NOT NULL,
        notes       TEXT    NOT NULL DEFAULT '',
        updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE(league_id, season_id, week_number)
    )
""")

con.commit()
con.close()
print('Done — week_notes table created.')

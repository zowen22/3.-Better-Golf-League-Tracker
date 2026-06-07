"""
Migration: add per-player email preference columns to the players table.

Columns added:
  email_opt_out              INTEGER DEFAULT 0  -- blanket opt-out (already referenced in _get_player_emails)
  email_opt_out_round_results INTEGER DEFAULT 0  -- opt out of personal round-result scorecard emails
  email_opt_out_reminders    INTEGER DEFAULT 0  -- opt out of pre-round reminder emails

Run once:
  cd D:\GolfLeague\app && python migrate_email_prefs.py
"""
import os
import shutil
import sqlite3

DB_SRC = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_SRC = os.path.abspath(DB_SRC)
DB_TMP = '/tmp/golf_league_email_prefs.db'

print(f'Source DB: {DB_SRC}')

shutil.copy2(DB_SRC, DB_TMP)
con = sqlite3.connect(DB_TMP)
cur = con.cursor()

cols_to_add = [
    ('email_opt_out',               'INTEGER DEFAULT 0'),
    ('email_opt_out_round_results', 'INTEGER DEFAULT 0'),
    ('email_opt_out_reminders',     'INTEGER DEFAULT 0'),
]

existing = {row[1] for row in cur.execute("PRAGMA table_info(players)").fetchall()}

added = []
for col, col_def in cols_to_add:
    if col not in existing:
        cur.execute(f'ALTER TABLE players ADD COLUMN {col} {col_def}')
        added.append(col)
        print(f'  + Added column: {col}')
    else:
        print(f'  ~ Already exists: {col}')

con.commit()
con.close()

# Write back to Windows mount using open()+write()+fsync()
with open(DB_TMP, 'rb') as f:
    data = f.read()
with open(DB_SRC, 'wb') as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())

print(f'\nDone. Columns added: {added if added else "none (already existed)"}')

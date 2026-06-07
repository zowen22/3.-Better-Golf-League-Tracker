"""
Migration: player_nicknames table
Run: cd D:\GolfLeague\app && python migrate_player_nicknames.py
"""
import sqlite3, os, shutil, time

DB_SRC = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_SRC = os.path.abspath(DB_SRC)
BACKUP = DB_SRC + f'.bak_{int(time.time())}'

shutil.copy2(DB_SRC, BACKUP)
print(f"Backup: {BACKUP}")

conn = sqlite3.connect(DB_SRC)
cur = conn.cursor()

# Create player_nicknames table
cur.execute("""
CREATE TABLE IF NOT EXISTS player_nicknames (
    nickname_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    league_id    INTEGER NOT NULL,
    nickname     TEXT NOT NULL,
    is_primary   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now'))
)
""")

# Index for fast lookup by player
cur.execute("CREATE INDEX IF NOT EXISTS idx_pn_player ON player_nicknames(player_id)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_pn_league ON player_nicknames(league_id)")

conn.commit()
conn.close()
print("Done — player_nicknames table created.")

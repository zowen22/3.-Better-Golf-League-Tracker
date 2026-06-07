"""
Migration: create sub_requests table for player-initiated sub requests.
Run once: python migrate_sub_requests.py
"""
import shutil, sqlite3, os, sys

DB_SRC = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_SRC = os.path.abspath(DB_SRC)
DB_TMP = '/tmp/golf_migrate_sub.db'

shutil.copy(DB_SRC, DB_TMP)
conn = sqlite3.connect(DB_TMP)
c = conn.cursor()

# Check if already exists
existing = c.execute("SELECT name FROM sqlite_master WHERE name='sub_requests'").fetchone()
if existing:
    print("sub_requests table already exists — nothing to do.")
    conn.close()
    sys.exit(0)

c.executescript("""
CREATE TABLE sub_requests (
    request_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id      INTEGER NOT NULL,
    season_id      INTEGER NOT NULL,
    matchup_id     INTEGER NOT NULL,
    player_id      INTEGER NOT NULL,
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    sub_player_id  INTEGER,
    admin_notes    TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (matchup_id)    REFERENCES matchups(matchup_id),
    FOREIGN KEY (player_id)     REFERENCES players(player_id),
    FOREIGN KEY (sub_player_id) REFERENCES players(player_id)
);
CREATE INDEX idx_sub_requests_league ON sub_requests(league_id, status);
CREATE INDEX idx_sub_requests_matchup ON sub_requests(matchup_id);
""")

conn.commit()
conn.close()
shutil.copy(DB_TMP, DB_SRC)
print("Migration complete: sub_requests table created.")

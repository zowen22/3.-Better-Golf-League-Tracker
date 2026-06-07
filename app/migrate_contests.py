"""
Migration: add contest_results table (contests table already exists in DB).
Run once from D:\\GolfLeague\\app: python migrate_contests.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Database', 'golf_league.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    if 'contest_results' not in tables:
        cur.executescript("""
            CREATE TABLE contest_results (
                result_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id  INTEGER NOT NULL REFERENCES contests(contest_id) ON DELETE CASCADE,
                player_id   INTEGER NOT NULL,
                value_text  TEXT,
                notes       TEXT,
                rank        INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX idx_contest_results_contest ON contest_results(contest_id);
        """)
        conn.commit()
        print("contest_results table created.")
    else:
        print("Already exists, no action needed.")
    conn.close()

if __name__ == '__main__':
    run()

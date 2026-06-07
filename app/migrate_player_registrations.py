"""
Migration: player_registrations table
Run: cd D:\GolfLeague\app && python migrate_player_registrations.py
"""
import sqlite3, sys, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '..', 'Database', 'golf_league.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS player_registrations (
            reg_id              INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id           TEXT    NOT NULL,
            first_name          TEXT    NOT NULL,
            last_name           TEXT    NOT NULL,
            email               TEXT,
            starting_handicap   REAL    DEFAULT 0,
            message             TEXT,
            status              TEXT    DEFAULT 'pending',
            created_at          TEXT    NOT NULL,
            reviewed_at         TEXT,
            reviewed_by_user_id INTEGER,
            player_id           INTEGER,
            FOREIGN KEY (league_id) REFERENCES leagues(league_id)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_player_reg_league_status ON player_registrations(league_id, status)")

    # Add registration settings columns to leagues table
    for col, defn in [
        ('reg_enabled',     'INTEGER DEFAULT 0'),
        ('reg_welcome_msg', 'TEXT DEFAULT NULL'),
    ]:
        try:
            c.execute(f"ALTER TABLE leagues ADD COLUMN {col} {defn}")
            print(f"  + leagues.{col}")
        except sqlite3.OperationalError as e:
            if 'duplicate column' in str(e).lower():
                print(f"  = leagues.{col} (already exists)")
            else:
                raise

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    run()

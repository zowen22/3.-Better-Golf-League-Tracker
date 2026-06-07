"""
Migration: add email_opt_out column to players table.
Run once: cd D:\GolfLeague\app && python migrate_email_opt_out.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def run():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cols = [row[1] for row in cur.execute("PRAGMA table_info(players)").fetchall()]
    if 'email_opt_out' not in cols:
        cur.execute("ALTER TABLE players ADD COLUMN email_opt_out INTEGER NOT NULL DEFAULT 0")
        con.commit()
        print("Added email_opt_out column to players.")
    else:
        print("email_opt_out already exists — nothing to do.")
    con.close()

if __name__ == '__main__':
    run()

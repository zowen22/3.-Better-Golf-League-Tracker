"""
Migration: Add score_submissions and score_submission_details tables
for the Self-Reporting feature.

Run from D:\GolfLeague\app\:
    python migrate_add_score_submissions.py
"""

import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')

def main():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # score_submissions — one row per player submission (pending / approved / rejected)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS score_submissions (
            submission_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            matchup_id       INTEGER NOT NULL,
            season_id        INTEGER NOT NULL,
            submitter_name   TEXT,
            course_id        INTEGER,
            tee_id           INTEGER,
            round_date       TEXT,
            submitted_at     TEXT,
            status           TEXT NOT NULL DEFAULT 'pending',
            admin_note       TEXT,
            reviewed_at      TEXT,
            FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
            FOREIGN KEY (season_id)  REFERENCES seasons(season_id)
        )
    """)
    print("score_submissions: OK")

    # score_submission_details — one row per (submission, player, hole)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS score_submission_details (
            detail_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id    INTEGER NOT NULL,
            player_id        INTEGER NOT NULL,
            hole_number      INTEGER NOT NULL,
            gross_score      INTEGER NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES score_submissions(submission_id),
            FOREIGN KEY (player_id)     REFERENCES players(player_id)
        )
    """)
    print("score_submission_details: OK")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    main()

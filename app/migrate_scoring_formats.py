"""
Migration: add Best Ball + Team Totals + Classical Stroke Play point settings
to league_settings, and widen scoring_mode's documented valid values (no
schema change needed for that -- it's already a free-text column with no
CHECK constraint).

Run from app/ with DATABASE_URL set:
    DATABASE_URL=<your-db-url> python migrate_scoring_formats.py

Or run this SQL directly:
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS best_ball_points_per_hole   REAL NOT NULL DEFAULT 2.0;
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS best_ball_tie_points        REAL NOT NULL DEFAULT 1.0;
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS best_ball_overall_point     REAL NOT NULL DEFAULT 2.0;
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS team_totals_points_per_hole REAL NOT NULL DEFAULT 2.0;
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS team_totals_tie_points      REAL NOT NULL DEFAULT 1.0;
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS team_totals_overall_point   REAL NOT NULL DEFAULT 2.0;
    ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS classical_stroke_play_points_per_stroke REAL NOT NULL DEFAULT 1.0;
"""
import os
import sys

NEW_COLUMNS = [
    ('best_ball_points_per_hole',   'REAL NOT NULL DEFAULT 2.0'),
    ('best_ball_tie_points',        'REAL NOT NULL DEFAULT 1.0'),
    ('best_ball_overall_point',     'REAL NOT NULL DEFAULT 2.0'),
    ('team_totals_points_per_hole', 'REAL NOT NULL DEFAULT 2.0'),
    ('team_totals_tie_points',      'REAL NOT NULL DEFAULT 1.0'),
    ('team_totals_overall_point',   'REAL NOT NULL DEFAULT 2.0'),
    ('classical_stroke_play_points_per_stroke', 'REAL NOT NULL DEFAULT 1.0'),
]


def run():
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        print("ERROR: DATABASE_URL not set. Set it before running this migration.", file=sys.stderr)
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    added = []
    for col_name, col_def in NEW_COLUMNS:
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'league_settings'
                 AND column_name = %s""",
            (col_name,)
        )
        if cur.fetchone():
            continue
        cur.execute(f"ALTER TABLE league_settings ADD COLUMN {col_name} {col_def}")
        added.append(col_name)

    if added:
        conn.commit()
        print(f"Added columns: {', '.join(added)}")
    else:
        print("All columns already exist -- nothing to do.")

    cur.close()
    conn.close()


if __name__ == '__main__':
    run()

-- Week Exclusions -- see Plans/2026-09-11-week-exclusions-technical-spec.md.
-- Lets an admin exclude a specific (season, week) from Stats/Handicap/Points
-- independently. Week-level (not matchup-level) on purpose -- a matchup-level
-- flag would need setting on every matchup row in that week individually,
-- exactly the fragility the 2026-09-05 bye-convention bug already exposed
-- when a newly-added matchup silently missed a flag existing rows had.
-- Opt-in row: no row for a (season_id, week_number) means nothing excluded.
-- Additive + idempotent.
CREATE TABLE IF NOT EXISTS week_exclusions (
    exclusion_id       SERIAL PRIMARY KEY,
    season_id           INTEGER NOT NULL REFERENCES seasons(season_id),
    week_number         INTEGER NOT NULL,
    exclude_stats       INTEGER NOT NULL DEFAULT 0,
    exclude_handicap    INTEGER NOT NULL DEFAULT 0,
    exclude_points      INTEGER NOT NULL DEFAULT 0,
    reason              TEXT,
    updated_by_user_id  INTEGER REFERENCES users(user_id),
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (season_id, week_number)
);
CREATE INDEX IF NOT EXISTS idx_week_exclusions_season_week ON week_exclusions(season_id, week_number);

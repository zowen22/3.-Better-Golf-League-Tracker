-- Manual points override -- see Plans/2026-08-09-points-override-technical-spec.md.
-- match_results is deleted+reinserted by every recompute, so an override
-- can't live as a column there -- it lives here, append-only, and gets
-- reapplied by scores.apply_point_overrides() after every match_results
-- write. Additive + idempotent.
CREATE TABLE IF NOT EXISTS point_overrides (
    override_id SERIAL PRIMARY KEY,
    matchup_id INTEGER NOT NULL REFERENCES matchups(matchup_id),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    team_id INTEGER,
    field TEXT NOT NULL,
    original_value REAL NOT NULL,
    override_value REAL NOT NULL,
    reason TEXT NOT NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active INTEGER NOT NULL DEFAULT 1,
    cleared_by_user_id INTEGER REFERENCES users(user_id),
    cleared_at TIMESTAMPTZ,
    cleared_reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS point_overrides_active_uniq
    ON point_overrides(matchup_id, player_id, field) WHERE active = 1;
CREATE INDEX IF NOT EXISTS idx_point_overrides_matchup ON point_overrides(matchup_id);

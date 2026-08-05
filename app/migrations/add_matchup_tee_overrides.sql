-- Per-matchup, per-player tee reassignment made from the print-scorecards
-- screen ("last minute" tee change before scores exist). Separate from
-- player_absences on purpose: a tee change is not an absence, and reusing
-- that table's row-existence-means-absent semantics would leak into every
-- absence-driven scoring query in scores.py. Read at score-entry prefill
-- time (player_default_tees) so the change survives into actual scoring.
CREATE TABLE IF NOT EXISTS matchup_tee_overrides (
    override_id SERIAL PRIMARY KEY,
    matchup_id  INTEGER NOT NULL REFERENCES matchups(matchup_id),
    player_id   INTEGER NOT NULL REFERENCES players(player_id),
    tee_id      INTEGER NOT NULL REFERENCES tees(tee_id),
    UNIQUE(matchup_id, player_id)
);

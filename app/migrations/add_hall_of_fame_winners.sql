-- Hall of Fame: admin-curated, cross-season custom awards (GLT #5).
-- Fixed-slot version -- award_slot is a plain TEXT enum validated at the
-- app layer, not a separate award_types table. Additive + idempotent.
CREATE TABLE IF NOT EXISTS hall_of_fame_winners (
    winner_id    SERIAL PRIMARY KEY,
    league_id    INTEGER NOT NULL REFERENCES leagues(league_id),
    season_id    INTEGER NOT NULL REFERENCES seasons(season_id),
    award_slot   TEXT NOT NULL,
    award_label  TEXT,
    player_id    INTEGER REFERENCES players(player_id),
    team_id      INTEGER REFERENCES teams(team_id),
    winner_name  TEXT,
    notes        TEXT,
    created_date TEXT DEFAULT CURRENT_DATE
);
CREATE INDEX IF NOT EXISTS idx_hall_of_fame_winners_league ON hall_of_fame_winners(league_id);
CREATE INDEX IF NOT EXISTS idx_hall_of_fame_winners_season ON hall_of_fame_winners(season_id);

CREATE TABLE IF NOT EXISTS round_reflections (
    reflection_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    odds_and_ends TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_id, season_id, week_number)
);

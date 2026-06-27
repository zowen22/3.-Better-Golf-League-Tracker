ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS scoring_mode TEXT NOT NULL DEFAULT 'match_play';

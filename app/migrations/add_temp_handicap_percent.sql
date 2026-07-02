ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS temp_handicap_percent_member REAL NOT NULL DEFAULT 90.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS temp_handicap_percent_sub REAL NOT NULL DEFAULT 90.0;

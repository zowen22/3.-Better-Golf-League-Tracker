ALTER TABLE league_settings
    ADD COLUMN IF NOT EXISTS show_dues_shame_widget INTEGER NOT NULL DEFAULT 0;

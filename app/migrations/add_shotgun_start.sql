-- Shotgun-start tee time templates -- see Plans/2026-08-13-shotgun-tee-time-technical-spec.md.
-- Additive + idempotent. league_settings gets an explicit on/off toggle
-- (not inferred from template presence -- per @user, this changes what
-- the per-week tee_time/starting_hole fields mean, not just whether a
-- template exists). matchups.slot_number is nullable and unused unless
-- Shotgun Start is on for the season.
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS shotgun_start_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matchups ADD COLUMN IF NOT EXISTS slot_number INTEGER;

CREATE TABLE IF NOT EXISTS shotgun_slot_templates (
    template_id     SERIAL PRIMARY KEY,
    season_id       INTEGER NOT NULL REFERENCES seasons(season_id),
    slot_number     INTEGER NOT NULL,
    slot_label      TEXT,
    tee_time        TEXT,
    front_nine_hole INTEGER,
    back_nine_hole  INTEGER,
    UNIQUE (season_id, slot_number, slot_label)
);
CREATE INDEX IF NOT EXISTS idx_shotgun_slot_templates_season ON shotgun_slot_templates(season_id);

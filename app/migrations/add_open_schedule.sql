-- Open Schedule: opt-in freeform match creation by members. Any member can
-- create a brand-new match at any time (pick an opponent team + a date, no
-- approval queue, no completeness guarantee) instead of the admin-generated
-- round-robin. Season-scoped boolean matching shotgun_start_enabled's
-- precedent exactly.
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS open_schedule_enabled INTEGER NOT NULL DEFAULT 0;

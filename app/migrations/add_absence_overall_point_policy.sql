ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS absence_overall_point_policy TEXT NOT NULL DEFAULT 'excused_only';

-- trigger_round_id/is_manual_override/override_reason/override_by_user_id/override_at
-- were added directly to the live DB at some point without ever being captured in
-- schema_postgres.sql or a migration file. Documenting them here (safe no-op where
-- they already exist) plus the new pre_override_* snapshot columns.
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS trigger_round_id INTEGER;
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS is_manual_override INTEGER NOT NULL DEFAULT 0;
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS override_reason TEXT;
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS override_by_user_id INTEGER;
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS override_at TEXT;

-- Snapshot of the calculated value/reason a manual override replaced, so the
-- Handicap History page can show "calculated X -> overridden to Y" instead of
-- silently losing the pre-override value.
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS pre_override_index REAL;
ALTER TABLE handicap_history ADD COLUMN IF NOT EXISTS pre_override_reason TEXT;

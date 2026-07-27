-- Self-service admin password reset (email a reset link to the League ID's
-- admin_email on file). Run in Supabase SQL Editor:
-- Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE leagues ADD COLUMN IF NOT EXISTS admin_email TEXT DEFAULT NULL;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

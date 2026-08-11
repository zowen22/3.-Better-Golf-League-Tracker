-- Individual-account password reset -- see Work Packages backlog
-- ("Individual accounts have no self-serve password reset", found 2026-08-11).
-- password_reset_tokens previously only supported league-admin resets
-- (league_id NOT NULL). A row now represents either kind: league_id set
-- for a league-admin reset (existing behavior, unchanged), or user_id set
-- for an individual-account reset (new) -- never both. Additive + idempotent.
ALTER TABLE password_reset_tokens ALTER COLUMN league_id DROP NOT NULL;
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(user_id);

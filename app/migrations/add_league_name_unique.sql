-- Add a case-insensitive UNIQUE index on leagues.league_name, closing the
-- TOCTOU race in auth.create_league() (which already checks case-insensitively
-- via a parameterized LOWER() comparison, but only at the app layer).
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run
-- If this errors on a duplicate, resolve the conflicting league_name(s) first:
--   SELECT LOWER(league_name), COUNT(*) FROM leagues GROUP BY 1 HAVING COUNT(*) > 1;

CREATE UNIQUE INDEX IF NOT EXISTS ux_leagues_league_name_ci ON leagues(LOWER(league_name));

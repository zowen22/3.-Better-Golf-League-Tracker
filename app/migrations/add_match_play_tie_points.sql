-- Match Play was missing a tie-points setting entirely (unlike Best Ball /
-- Team Totals, which each already have a full win/tie/overall triple).
-- Adds it, and aligns the win/overall column DEFAULTs with the value this
-- app has always actually used everywhere else (calc_match_play's hardcoded
-- fallback, and the admin settings form) -- these DEFAULTs only affect
-- NEWLY inserted rows that omit the column; no existing league's stored
-- values change.
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS match_play_tie_points REAL NOT NULL DEFAULT 1.0;
ALTER TABLE league_settings ALTER COLUMN match_play_points_per_hole SET DEFAULT 2;
ALTER TABLE league_settings ALTER COLUMN match_play_overall_point SET DEFAULT 2;

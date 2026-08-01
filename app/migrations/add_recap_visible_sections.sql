-- Admin-configurable set of stat sections shown to members on the
-- Week Recap page (schedule.week_summary). Comma-separated subset of:
-- eagles,birdies,low_gross,match_points,skins,standings. Admins always
-- see every section regardless of this setting (schedule.py week_summary()).
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS recap_visible_sections TEXT NOT NULL DEFAULT 'eagles,birdies,low_gross,match_points,skins,standings';

-- Admin-configurable display style for how teams are labeled in the
-- member dashboard's standings snapshot widget: 'team_name' (default,
-- falls back to last names if the team has none set), 'first_names',
-- or 'last_names'. Only affects that one widget (main.py dashboard()).
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS standings_name_style TEXT NOT NULL DEFAULT 'team_name';

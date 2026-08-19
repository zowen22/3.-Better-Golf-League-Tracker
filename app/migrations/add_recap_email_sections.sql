-- Admin's last-arranged "Sections to Include" order + checked state for the
-- Week Recap page's compose/send panel (schedule.week_summary), plus the
-- Standings tile's Record/Rounds sub-toggles. Format: comma-separated
-- "key:0" / "key:1" pairs, e.g. "header:1,standings:1,handicaps:0,...".
-- NULL/empty means "not customized yet" -- falls back to the built-in
-- default order (RECAP_EMAIL_SECTIONS_META in routes/email_config.py).
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS recap_email_sections TEXT;

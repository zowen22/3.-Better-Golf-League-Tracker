-- Admin control over member-dashboard widget visibility.
-- Four per-widget booleans on league_settings (matching the existing
-- show_dues_shame_widget precedent). DEFAULT 1 = visible, so existing leagues
-- see no change. These gate the MEMBER view only; admins always see all
-- widgets on their own dashboard. See Audits/2026-07-04-dashboard-widget-visibility-investigation.md.
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS show_announcements_widget INTEGER NOT NULL DEFAULT 1;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS show_round_recap_widget INTEGER NOT NULL DEFAULT 1;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS show_activity_feed_widget INTEGER NOT NULL DEFAULT 1;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS show_league_activity_widget INTEGER NOT NULL DEFAULT 1;

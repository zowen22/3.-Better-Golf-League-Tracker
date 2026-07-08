-- Site Admin Dashboard v1 (read-only platform health).
-- Adds a single boolean flag on users for the platform-operator gate.
-- No UI to toggle this — set manually in the DB by @user. See
-- Audits/2026-07-04-site-admin-dashboard-investigation.md and
-- Handoffs/2026-07-06-site-admin-dashboard-v1.md.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_site_admin INTEGER NOT NULL DEFAULT 0;

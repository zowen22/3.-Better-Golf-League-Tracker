-- Full audit trail for Site Admin "view as league" impersonation.
-- See app/impersonation.py and schema_postgres.sql for the full column comment.
CREATE TABLE IF NOT EXISTS site_admin_audit_log (
    audit_id SERIAL PRIMARY KEY,
    site_admin_user_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    method TEXT,
    path TEXT,
    status_code INTEGER,
    detail TEXT,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    ref_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_site_admin_audit_league ON site_admin_audit_log(league_id, ts);
CREATE INDEX IF NOT EXISTS idx_site_admin_audit_session ON site_admin_audit_log(ref_id, ts);

-- First-party ad/referrer landing capture + pre-login navigation path.
-- See app/traffic.py and schema_postgres.sql for the full column comment.
CREATE TABLE IF NOT EXISTS traffic_events (
    event_id SERIAL PRIMARY KEY,
    visitor_id TEXT NOT NULL,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL DEFAULT 'pageview',
    path TEXT NOT NULL,
    is_landing INTEGER NOT NULL DEFAULT 0,
    referrer TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_term TEXT,
    utm_content TEXT,
    gclid TEXT,
    gbraid TEXT,
    wbraid TEXT,
    gad_campaignid TEXT,
    user_agent TEXT,
    ip TEXT,
    ref_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_traffic_events_visitor ON traffic_events(visitor_id, ts);
CREATE INDEX IF NOT EXISTS idx_traffic_events_landing ON traffic_events(is_landing, ts);

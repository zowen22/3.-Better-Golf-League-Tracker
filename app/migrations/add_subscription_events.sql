-- Append-only event log for trial/conversion metrics. subscriptions itself
-- only stores current state (overwritten by every webhook), so this is the
-- only place trial-start/conversion/cancellation history survives.
CREATE TABLE IF NOT EXISTS subscription_events (
    event_id    SERIAL PRIMARY KEY,
    league_id   INTEGER NOT NULL REFERENCES leagues(league_id),
    event_type  TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_subscription_events_league ON subscription_events(league_id);
CREATE INDEX IF NOT EXISTS idx_subscription_events_type ON subscription_events(event_type);

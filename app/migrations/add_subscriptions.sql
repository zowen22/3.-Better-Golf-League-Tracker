-- Stripe billing state, one row per league. Additive + idempotent.
-- Source of truth is Stripe (via webhooks) -- this table mirrors it, it
-- doesn't compute anything independently.
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id       SERIAL PRIMARY KEY,
    league_id              INTEGER NOT NULL UNIQUE REFERENCES leagues(league_id),
    stripe_customer_id      TEXT NOT NULL,
    stripe_subscription_id  TEXT UNIQUE,
    status                  TEXT NOT NULL DEFAULT 'incomplete',
    price_id                TEXT,
    trial_end               TEXT,
    current_period_end      TEXT,
    cancel_at_period_end    INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_league ON subscriptions(league_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

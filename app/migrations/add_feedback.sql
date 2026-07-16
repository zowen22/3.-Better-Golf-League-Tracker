-- Freeform feedback/feature-request submissions from the site-wide footer
-- widget. Not league-scoped reporting -- league_id/user_id are nullable
-- context, not required (the shared league-password login has no user_id).
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id  SERIAL PRIMARY KEY,
    league_id    INTEGER REFERENCES leagues(league_id),
    user_id      INTEGER REFERENCES users(user_id),
    message      TEXT NOT NULL,
    page_url     TEXT,
    submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_feedback_submitted_at ON feedback(submitted_at);

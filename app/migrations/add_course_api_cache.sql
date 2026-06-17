-- WP6.1: Course API response cache
CREATE TABLE IF NOT EXISTS course_api_cache (
    cache_id    SERIAL PRIMARY KEY,
    api_course_id INTEGER NOT NULL UNIQUE,
    response_json TEXT NOT NULL,
    fetched_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- WP6.2: API request log for rate-limit guard
CREATE TABLE IF NOT EXISTS api_request_log (
    log_id      SERIAL PRIMARY KEY,
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
    endpoint    TEXT NOT NULL,
    league_id   INTEGER,
    user_id     INTEGER,
    response_code INTEGER
);

CREATE INDEX IF NOT EXISTS idx_api_request_log_month
    ON api_request_log (DATE_TRUNC('month', requested_at));

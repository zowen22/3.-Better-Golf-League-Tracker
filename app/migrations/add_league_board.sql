-- League Board: commissioner announcements + emoji reactions
CREATE TABLE IF NOT EXISTS league_announcements (
    announcement_id SERIAL PRIMARY KEY,
    league_id       INTEGER NOT NULL REFERENCES leagues(league_id) ON DELETE CASCADE,
    author_user_id  INTEGER NOT NULL REFERENCES users(user_id),
    body            TEXT NOT NULL,
    is_pinned       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_league_announcements_league
    ON league_announcements (league_id, created_at DESC);

CREATE TABLE IF NOT EXISTS announcement_reactions (
    reaction_id     SERIAL PRIMARY KEY,
    announcement_id INTEGER NOT NULL REFERENCES league_announcements(announcement_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    emoji           TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (announcement_id, user_id, emoji)
);

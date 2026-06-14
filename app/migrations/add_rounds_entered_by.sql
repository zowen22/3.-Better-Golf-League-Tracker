ALTER TABLE rounds ADD COLUMN IF NOT EXISTS entered_by_user_id INTEGER REFERENCES users(user_id);

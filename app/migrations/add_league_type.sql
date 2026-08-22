-- League vs. one-time Event/Tournament classification, chosen at league
-- creation. Copy/onboarding only -- nothing behaves differently based on
-- this, it just tailors wording. See "League vs. Event Onboarding" in
-- Technical Reference.
ALTER TABLE leagues ADD COLUMN IF NOT EXISTS league_type TEXT NOT NULL DEFAULT 'league';

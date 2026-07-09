-- Team Low Net contest type: contest_results can now represent either a
-- player-scoped result (existing individual contest types) or a
-- team-scoped result (new computed team contest types). Exactly one of
-- player_id/team_id is set per row, enforced at the application layer.
-- Additive + idempotent.
ALTER TABLE contest_results ALTER COLUMN player_id DROP NOT NULL;
ALTER TABLE contest_results ADD COLUMN IF NOT EXISTS team_id INTEGER REFERENCES teams(team_id);

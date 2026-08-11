-- Multi-league individual accounts -- see
-- Plans/2026-08-11-multi-league-individual-accounts-technical-spec.md.
-- user_league_roles already allowed multiple leagues per user_id with no
-- schema change needed, but had no constraint stopping two rows for the
-- same (user_id, league_id) pair. The Add League flow's app-level
-- "update instead of insert" logic makes that unreachable in practice, but
-- this makes it a real guarantee rather than trusting the application
-- layer alone. Additive + idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS ux_user_league_roles_user_league
    ON user_league_roles(user_id, league_id);

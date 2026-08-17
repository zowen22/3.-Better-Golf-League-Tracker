-- Whole-week skins (per @user, 2026-08-17): a single skins pot/winner set
-- now spans every matchup in a (season, week) -- the whole field playing
-- that week -- instead of just one foursome's own round. Previously
-- round_skins_settings/round_skins_participants/skins_results/
-- round_skins_flight_carryover were keyed by round_id, where one "round" =
-- one matchup (rounds.matchup_id is UNIQUE) -- so a "skins round" was
-- really just one foursome's pot, not the week's.
--
-- Verified zero rows in all four tables across every production league
-- (including Buckeye, who have skins_config/flights configured but never
-- actually ran a round through the old per-matchup flow) before writing
-- this -- pure schema change, nothing to migrate. Guarded on round_id
-- still existing so this is a no-op on every run after the first (this
-- file re-runs on every app startup, like every other additive migration).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'round_skins_settings' AND column_name = 'round_id'
    ) THEN
        DROP TABLE IF EXISTS round_skins_flight_carryover;
        DROP TABLE IF EXISTS skins_results;
        DROP TABLE IF EXISTS round_skins_participants;
        DROP TABLE IF EXISTS round_skins_settings;

        CREATE TABLE round_skins_settings (
            setting_id SERIAL PRIMARY KEY,
            season_id INTEGER NOT NULL REFERENCES seasons(season_id),
            week_number INTEGER NOT NULL,
            amount_override REAL,
            gross_net_override TEXT,
            carried_over_amount REAL NOT NULL DEFAULT 0,
            notes TEXT,
            UNIQUE (season_id, week_number)
        );

        CREATE TABLE round_skins_participants (
            participant_id SERIAL PRIMARY KEY,
            season_id INTEGER NOT NULL REFERENCES seasons(season_id),
            week_number INTEGER NOT NULL,
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            paid_in INTEGER NOT NULL DEFAULT 0,
            amount_paid REAL,
            UNIQUE (season_id, week_number, player_id)
        );

        CREATE TABLE skins_results (
            skin_id SERIAL PRIMARY KEY,
            season_id INTEGER NOT NULL REFERENCES seasons(season_id),
            week_number INTEGER NOT NULL,
            hole_number INTEGER NOT NULL,
            winner_player_id INTEGER REFERENCES players(player_id),
            skins_won INTEGER,
            payout REAL,
            carried_over INTEGER NOT NULL DEFAULT 0,
            -- NULL = non-flighted result (preserves the pre-existing meaning).
            flight INTEGER DEFAULT NULL
        );

        -- Per-flight, per-week carryover (parallel to
        -- round_skins_settings.carried_over_amount, which stays as the
        -- single-pot carryover value for the non-flighted path).
        CREATE TABLE round_skins_flight_carryover (
            carryover_id SERIAL PRIMARY KEY,
            season_id INTEGER NOT NULL REFERENCES seasons(season_id),
            week_number INTEGER NOT NULL,
            flight INTEGER NOT NULL,
            carried_over_amount REAL NOT NULL DEFAULT 0,
            UNIQUE (season_id, week_number, flight)
        );
    END IF;
END $$;

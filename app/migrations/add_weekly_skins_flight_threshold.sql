-- Skins Flights, set per week (per @user 2026-08-18): the weekly skins
-- setup form gets its own Enable + one threshold control, stored on
-- round_skins_settings (already season_id/week_number-scoped) rather than
-- read from the season-wide skins_config.flights_enabled/
-- skins_flight_thresholds. The multi-threshold calculation engine is
-- unchanged/still used -- flight_threshold just feeds it as a
-- single-value list (-> 2 flights, Low/High) since that's all this form
-- exposes for now.
ALTER TABLE round_skins_settings ADD COLUMN IF NOT EXISTS flights_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE round_skins_settings ADD COLUMN IF NOT EXISTS flight_threshold REAL;

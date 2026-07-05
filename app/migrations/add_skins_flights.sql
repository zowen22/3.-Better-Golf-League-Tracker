-- Skins Flights: handicap-tiered skins pots (Handoffs/2026-07-04-skins-flights.md).
-- Config lives on skins_config — verified as the table the live round_view/calculate
-- path in skins.py actually reads (league_settings.skins_default_* is written by the
-- Admin Settings page but never read by skins.py; see Execution Report for detail).
ALTER TABLE skins_config ADD COLUMN IF NOT EXISTS flights_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE skins_config ADD COLUMN IF NOT EXISTS flight_threshold_low REAL;
ALTER TABLE skins_config ADD COLUMN IF NOT EXISTS flight_threshold_high REAL;

-- NULL = non-flighted result (preserves all existing rows' meaning unchanged).
ALTER TABLE skins_results ADD COLUMN IF NOT EXISTS flight INTEGER DEFAULT NULL;

-- Per-flight, per-round carryover (parallel to round_skins_settings.carried_over_amount,
-- which stays as the single-pot carryover value for the non-flighted path).
CREATE TABLE IF NOT EXISTS round_skins_flight_carryover (
    carryover_id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL,
    flight INTEGER NOT NULL,
    carried_over_amount REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    UNIQUE (round_id, flight)
);

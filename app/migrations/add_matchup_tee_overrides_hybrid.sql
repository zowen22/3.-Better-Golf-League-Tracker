-- Support a per-player "hybrid" tee reassignment (e.g. "Whites on par 3s,
-- Blacks elsewhere") from the print-scorecards popover. tee_id stays the
-- single "real" tee used for scoring prefill (enter_week never needs to
-- know about tee_id_2 — the app has no per-hole-per-player tee assignment
-- anywhere in the schema, see matchup_tee_overrides' own comment); tee_id_2
-- is purely for the combined "A/B" display label when both are set.
ALTER TABLE matchup_tee_overrides ADD COLUMN IF NOT EXISTS tee_id_2 INTEGER REFERENCES tees(tee_id);

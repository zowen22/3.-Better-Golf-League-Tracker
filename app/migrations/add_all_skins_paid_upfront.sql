-- League-wide toggle: when on, skins buy-ins are assumed paid for the
-- whole season up front, and the weekly score-entry page shows an in/out
-- checkbox per player instead of requiring a full Skins Setup form visit.
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS all_skins_paid_upfront INTEGER NOT NULL DEFAULT 0;

-- ab_designation_method was fully vestigial: no A/B pairing/scoring logic
-- anywhere in the codebase ever read it (verified 2026-07-10, see
-- Plans/2026-07-10-dead-settings-resolution.md). Dropping the column --
-- app code, admin settings UI, and the public League Info display were
-- all updated in the same pass to stop reading/writing it.
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE league_settings DROP COLUMN IF EXISTS ab_designation_method;

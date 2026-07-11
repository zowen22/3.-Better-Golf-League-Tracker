-- skins_config.handicap_percent was fully dead: no admin UI field ever
-- existed for it, and _calculate_skins() (routes/skins.py) always reads
-- net_score straight from the already-stored hole_scores row (computed at
-- normal score-entry time using the league's regular handicap_percent) --
-- never a separate skins-specific recompute. Verified 2026-07-10, see
-- Plans/2026-07-10-dead-settings-resolution.md. @user decided to drop it
-- rather than build the (nontrivial -- would need a genuinely read-only
-- point-in-time handicap-index helper) real implementation.
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE skins_config DROP COLUMN IF EXISTS handicap_percent;

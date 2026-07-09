-- Recurring ("every week") contests + richer per-result reporting columns,
-- matching GLT's own Contest Winners report layout (Contest Name, Week #,
-- Date, Course, Contest Winner, Hole #, Distance, Amount Won, Comments —
-- Date/Course are derived from matchups at query time, not stored here).
--
-- contests.is_recurring: when set, the contest applies every week rather
-- than one fixed week_num; contest_results.week_num then carries each
-- individual result's own week so a recurring contest can accumulate one
-- set of results per week over the season.
--
-- Additive + idempotent.
ALTER TABLE contests ADD COLUMN IF NOT EXISTS is_recurring INTEGER NOT NULL DEFAULT 0;
ALTER TABLE contest_results ADD COLUMN IF NOT EXISTS week_num INTEGER;
ALTER TABLE contest_results ADD COLUMN IF NOT EXISTS distance TEXT;
ALTER TABLE contest_results ADD COLUMN IF NOT EXISTS amount_won NUMERIC;

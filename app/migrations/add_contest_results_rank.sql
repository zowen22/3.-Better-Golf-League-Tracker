-- Add the `rank` column the app has always expected on contest_results.
--
-- The contests feature writes this column (INSERT in routes/contests.py),
-- orders results by it (season_view / admin_edit queries), and renders it as
-- 1st/2nd/3rd medals in the templates — but it was never added to
-- schema_postgres.sql, so on Postgres `ORDER BY cr.rank` is misparsed as the
-- built-in ordered-set aggregate rank() and every /contests page 500s with
-- "WITHIN GROUP is required for ordered-set aggregate rank". Additive + idempotent.
ALTER TABLE contest_results ADD COLUMN IF NOT EXISTS rank INTEGER;

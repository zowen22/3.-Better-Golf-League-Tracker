-- Centralizes "what counts as a real, finished round with a real gross
-- total" -- the definition had drifted independently at multiple call
-- sites (records.py's season leaders, career average, and best/worst
-- gross round records; stats.py's season-stats low-gross card), each
-- retyping is_absent/status/min-holes guards slightly differently and
-- twice missing one entirely. One row per scorecard that actually
-- counts. CREATE OR REPLACE VIEW is idempotent -- safe to re-run.
CREATE OR REPLACE VIEW valid_round_gross AS
SELECT
    sc.scorecard_id,
    sc.player_id,
    sc.team_id,
    r.round_id,
    r.course_id,
    m.matchup_id,
    m.season_id,
    m.week_number,
    m.scheduled_date,
    s.league_id,
    gt.total_gross,
    gt.holes_recorded
FROM scorecards sc
JOIN rounds r    ON sc.round_id   = r.round_id
JOIN matchups m  ON r.matchup_id  = m.matchup_id
JOIN seasons s   ON m.season_id   = s.season_id
JOIN (
    SELECT scorecard_id, SUM(gross_score) AS total_gross, COUNT(*) AS holes_recorded
    FROM hole_scores
    GROUP BY scorecard_id
    HAVING COUNT(*) >= 9
) gt ON gt.scorecard_id = sc.scorecard_id
WHERE sc.is_absent = 0
  AND m.is_bye      = 0
  AND m.status      = 'completed'
  -- Week Exclusions (see Plans/2026-09-11-week-exclusions-technical-spec.md):
  -- a week with exclude_stats=1 doesn't count as a "valid round" for any
  -- stats-domain consumer of this view.
  AND NOT EXISTS (
      SELECT 1 FROM week_exclusions we
      WHERE we.season_id = m.season_id AND we.week_number = m.week_number
        AND we.exclude_stats = 1
  );

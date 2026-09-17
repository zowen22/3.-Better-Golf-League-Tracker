-- hole_scores had no uniqueness guard on (scorecard_id, hole_number) -- a
-- duplicate row for the same hole (possible if any write path ever failed
-- to clear the old row before inserting a replacement) would silently
-- double-count into every SUM-based stat built on hole_scores: gross/net
-- totals, eagle/birdie/par/bogey counts, hole averages, etc. Repairs any
-- existing duplicates first (keeps the most recently written row per
-- scorecard+hole, drops the rest), then adds the unique index so this
-- can't recur. CREATE UNIQUE INDEX IF NOT EXISTS is idempotent -- safe to
-- re-run.
DELETE FROM hole_scores a
USING hole_scores b
WHERE a.scorecard_id = b.scorecard_id
  AND a.hole_number   = b.hole_number
  AND a.hole_score_id < b.hole_score_id;

CREATE UNIQUE INDEX IF NOT EXISTS hole_scores_scorecard_hole_uniq
    ON hole_scores (scorecard_id, hole_number);

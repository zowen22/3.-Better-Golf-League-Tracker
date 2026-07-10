# Technical Spec: Scoring History (GLT-matched columns) + Scoring by Year

*Status: `Ready to build` — @user 2026-07-10: "Let's do scoring history and scoring by year the way GLT does it."*
*Decision doc this spec implements: `Plans/2026-07-09-player-scoring-detail-enhancements.md`*

-----

## Important correction before this spec starts

The original stats-parity assessment (`7. GLT Feature Parity.md` #7, and this plan's own "Current BGLT state") claimed BGLT had **no** hole-by-hole detail per round — only round totals. That was wrong. `players.py`'s `profile()` (lines 215–296) and `profile.html`'s "Hole-by-Hole Scoring History" section (lines 305–420+) already render a full per-round hole-by-hole table — one row per round, every hole's gross score, color-coded eagle/birdie/par/bogey/double, plus an average row and a birdie/par/bogey% row. This table predates the 2026-07-09 assessment (confirmed via `git log -S`, added in an earlier commit than that pass). So this is **not a build-from-scratch** item — it's an extension of an existing, working table.

## Goal

Match GLT's two pages as closely as BGLT's data model allows:
1. `individual/individual-scoring-detail` ("Scoring History") — add the columns GLT shows that BGLT's existing table doesn't: **Hdcp, Net, Pts, OUT/IN subtotals, Skins**.
2. `individual/scoring-average-by-year` ("Scoring by Year") — new page: per (Season, Course) for one player — rounds played, front/back net averages, scoring-category counts.

-----

## 1. Scoring History — extend the existing table

### Current state (exact, from the code)

`profile()`'s `hole_rows` query (lines 216–229) selects, per hole-score row: `r.round_id, r.round_date, m.week_number, m.season_id, s.season_name, hs.hole_number, hs.gross_score, h.par`. This is grouped into `rounds_by_id` (lines 232–250), each entry holding `{round_id, round_date, week_number, season_name, holes: {hole_number: {gross, par}}}`. The template renders one row per round from this structure — gross-only, no Hdcp/Net/Pts/Skins.

Separately, `round_data` (built earlier in the same function, lines 147–174) already computes **per round**: `hcp_used` (from `sc.handicap_at_time_of_play`), `net_total` (summed from `hole_scores.net_score`), and `total_pts` (from `match_results.total_points`) — but this list isn't threaded into `hole_rows`/`rounds_by_id`, so the hole-by-hole table can't currently show them.

### Design

Extend the existing `hole_rows` query (not a new query) to also select `sc.handicap_at_time_of_play AS hcp_used`, `hs.net_score`, `mr.total_points AS total_pts` (join `match_results` the same way `round_rows` already does at lines 137–139), and `t.nine` (from `tees`, via `r.tee_id`) so front/back can be identified for OUT/IN subtotals. Carry these into `rounds_by_id[rid]` once per round (they're constant across that round's hole rows) alongside the existing `holes` dict — no second query, no join to a separate dataset.

**OUT/IN subtotals**: sum `holes[1..9]` gross for "Out", `holes[10..18]` for "In" when `hole_columns` spans past 9 (18-hole league); for a 9-hole league (this project's typical case — `hole_columns` only 1–9), just show the existing single Total column, no separate Out/In split needed since there's only one 9. Determine which case applies from `max(hole_columns)`, not a hardcoded assumption — some leagues in this codebase are 18-hole (`holes_per_round` setting).

**Skins column**: new small query, `SELECT round_id, COUNT(*) AS skins_won FROM skins_results WHERE winner_player_id = %s AND round_id IN (...) GROUP BY round_id` (batched once for all this player's round_ids, not per-row) — merge into `rounds_by_id[rid]['skins_won']`, default 0 if the league doesn't use skins or the row is absent (graceful, matching how `nicknames`/`committee_adjustment` already handle "table not applicable" via `table_exists()`/try-except elsewhere in this same function).

**Rating/Slope**: GLT's row-level Rating/Slope belongs to the *tee actually played that round* — already resolvable via `r.tee_id → tees.rating/tees.slope`, add to the same extended query (`te.rating, te.slope`).

### Template changes

`profile.html`'s existing hole-history table (lines 305–420) gets 5 new columns appended after the hole grid, before/instead of the current single "Total" column: **Out | In** (or just **Total** for 9-hole leagues, per the design above), **Hdcp**, **Net**, **Pts**, **Skins**. Category counts (Eagle/Birdie/Par/Bogey/Double/Other) — GLT shows these as raw counts in a summary row; the existing table already shows them as **percentages** in the footer (birdie/par/bogey% row, lines 405–419). Recommend keeping percentages (more informative at a glance, and the underlying counts are already computed in `hole_avg_data`) rather than switching to GLT's raw-count style — flagging this as the one small style call being made without asking, since it's cosmetic and the data underneath is identical either way.

### Effort: S. No schema, no migration, no new query pattern — extends one existing query with 4 more columns + one small batched lookup query for skins.

-----

## 2. Scoring by Year — new page

**Route:** `players.scoring_by_year` → `GET /players/<int:player_id>/scoring-by-year`.

### Current state

Nothing today groups a player's rounds by (season, course). `profile()`'s `season_list` groups by season only (no course dimension). `stats.py`'s `course_stats()` groups by course across *all* players (no per-player, per-season dimension). This is a genuine new cross-tab, not an existing query with a wider GROUP BY — the closest prior art is `course_stats()`'s hole-level query shape, reused for the category-count logic.

### Design

One query, grouped by `(season_id, course_id, nine)`, for one player:

```sql
SELECT m.season_id, s.season_name, c.course_id, c.course_name, te.nine,
       COUNT(DISTINCT sc.scorecard_id) AS rounds,
       ROUND(AVG(net_per_round.net_total), 2) AS avg_net,
       SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score <= h.par - 2 THEN 1 ELSE 0 END) AS eagles,
       SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par - 1 THEN 1 ELSE 0 END) AS birdies,
       SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par     THEN 1 ELSE 0 END) AS pars,
       SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par + 1 THEN 1 ELSE 0 END) AS bogeys,
       SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par + 2 THEN 1 ELSE 0 END) AS doubles,
       SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score >= h.par + 3 THEN 1 ELSE 0 END) AS others
  FROM hole_scores hs
  JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
  JOIN rounds r       ON sc.round_id     = r.round_id
  JOIN matchups m     ON r.matchup_id    = m.matchup_id
  JOIN seasons s      ON m.season_id     = s.season_id
  JOIN courses c      ON r.course_id     = c.course_id
  JOIN tees te        ON r.tee_id        = te.tee_id
  LEFT JOIN holes h   ON hs.hole_id      = h.hole_id
 WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed' AND sc.is_absent = 0
 GROUP BY m.season_id, s.season_name, c.course_id, c.course_name, te.nine
 ORDER BY m.season_id DESC, c.course_name, te.nine
```

**Net average is per-round, not per-hole** — `AVG(hs.net_score)` inside this grouping would average per-hole net values, not per-round net totals, which is the wrong number (GLT's "front/back net average" is clearly a round-level stat: the average round score on that nine). This needs a subquery/CTE computing `net_total` per scorecard first (`SUM(hs.net_score) GROUP BY scorecard_id`), then averaging *that* — same pattern the existing `/compare` route already uses for `avg_gross` (lines 71–85 in `stats.py`, adapted from gross to net and re-scoped to one player). Sketch:

```sql
WITH per_round_net AS (
    SELECT sc.scorecard_id, sc.player_id, r.round_id, m.season_id, r.course_id, te.nine,
           SUM(hs.net_score) AS net_total
      FROM hole_scores hs
      JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
      JOIN rounds r       ON sc.round_id     = r.round_id
      JOIN matchups m     ON r.matchup_id    = m.matchup_id
      JOIN tees te        ON r.tee_id        = te.tee_id
     WHERE sc.player_id = %s AND sc.is_absent = 0 AND m.status = 'completed'
     GROUP BY sc.scorecard_id, sc.player_id, r.round_id, m.season_id, r.course_id, te.nine
)
SELECT prn.season_id, s.season_name, c.course_id, c.course_name, prn.nine,
       COUNT(*) AS rounds, ROUND(AVG(prn.net_total), 2) AS avg_net
  FROM per_round_net prn
  JOIN seasons s  ON prn.season_id = s.season_id AND s.league_id = %s
  JOIN courses c  ON prn.course_id = c.course_id
 GROUP BY prn.season_id, s.season_name, c.course_id, c.course_name, prn.nine
 ORDER BY prn.season_id DESC, c.course_name, prn.nine
```

Category counts (eagle/birdie/par/bogey/double/other) run as a **second** query, same `(season_id, course_id, nine)` grouping but at the hole level (the first query snippet above, minus the `avg_net` column) — join the two result sets by `(season_id, course_id, nine)` in Python, same merge pattern already used elsewhere in this codebase (e.g. `hole_averages()` building `player_holes`/`course_holes` as separate queries then zipping by key).

**Category counts: net or gross?** The plan doc's own GLT description doesn't specify, but since the averages on this page are explicitly net-based, use **net vs. par** (`hs.net_score - h.par`, not `hs.gross_score - h.par`) for eagle/birdie/par/bogey/double/other classification too — consistent with the rest of the page being a net-scoring view. Flagging this as the sensible default being made, not silently assumed.

### New template

`templates/players/scoring_by_year.html` — one table, grouped by season (most recent first), sub-rows per course/nine within that season: Season, Course, Nine (Front/Back/Full), Rounds, Net Avg, Eagle/Birdie/Par/Bogey/Double/Other counts. Linked from the player profile page (new "Scoring by Year" button/link near the existing Hole-by-Hole section).

### Effort: S–M. No schema, no migration — two grouped queries (one needs a per-round net-total subquery/CTE, not previously written anywhere in this shape) + one new template.

-----

## Testing plan

Same pattern as every build this session — validate against real dev Postgres, not just logic review.
- **Scoring History**: pick a real player/round already in the dev DB, hand-verify the new Hdcp/Net/Pts columns match that round's existing `scorecards.handicap_at_time_of_play`/summed `hole_scores.net_score`/`match_results.total_points` (all already displayed elsewhere on the same profile page in the round-history table above — cross-check for consistency, not recomputation).
- **Scoring by Year**: for a player with rounds at 2+ courses (or 2+ seasons, if course variety is thin in dev data), hand-sum net totals per round and average them per (season, course, nine) from raw `hole_scores`, compare against the route's output. Confirm the per-round-net-total CTE doesn't double-count when a player played multiple rounds at the same course/season (the actual case this query needs to get right — a naive `AVG(hs.net_score)` would silently produce a per-hole average, not a per-round one, if this validation step is skipped).

## Next step

Both ready to build. Category-summary style resolved 2026-07-10 — @user: keep the existing percentage-style footer as-is, not switching to GLT's raw-count style.

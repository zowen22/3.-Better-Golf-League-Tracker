# Classical Stroke Play Standings View — Technical Spec

**Status:** Decision: Go ahead (2026-07-10, @user) — Built & shipped 2026-07-10. Went with recommended Option (a): gated the existing `/standings/individual` page rather than building a separate route. The bug fix and the "leaderboard" need turned out to be the same change — the page's existing Rank/Total Pts/Pts-per-Round columns (already computed, already correct for any point-based format) already ARE the field-wide leaderboard once the meaningless Role/W-T-L columns are hidden for this format. Validated against real dev Postgres (temporarily switched season 1 to classical_stroke_play mode): Role/W-T-L columns correctly hidden, no template `None` leakage, match_play mode confirmed unaffected; reverted cleanly.
**Type:** Technical Spec
**Linked WP:** WP3.1 — flagged as a follow-up when Classical Stroke Play (Phase 3) shipped 2026-07-10: "no dedicated Classical Stroke Play leaderboard/standings view... existing team-oriented scorecard displays will render `role='FIELD'` rows but weren't redesigned for a field-wide format."
**Prepared by:** Claude, 2026-07-10

## Context

Classical Stroke Play (`Plans/2026-07-10-scoring-formats-technical-spec.md`, Phase 3) writes one `match_results` row per player per week with `role='FIELD'`, `opponent_player_id=NULL`, and `total_points`/`overall_point_won` both set to `(par − net) × points_per_stroke` — a genuinely field-wide, non-pairwise point value (can be any float: +4.0, −2.0, 0.0, etc.), unlike every other scoring mode where `overall_point_won` is always a normalized match-outcome value in `{0.0, 0.5, 1.0}`.

Team-level standings were already confirmed correct when Phase 3 shipped (`SUM(mr.total_points) GROUP BY team_id` is format-agnostic — a team's two Classical Stroke Play players' individual points sum into the team total exactly the same way any other format's points do). This spec covers what's still missing at the **player/week display level**.

## What's actually broken vs. what's just missing

Researching this spec surfaced a real, previously-unflagged **correctness bug**, not just a missing view:

**`standings.individual()` (`standings.py:1058-1092`) computes W-L-T like this:**
```sql
SUM(CASE WHEN mr.overall_point_won >= 1.0 THEN 1 ELSE 0 END) AS wins,
SUM(CASE WHEN mr.overall_point_won  = 0.5 THEN 1 ELSE 0 END) AS ties,
SUM(CASE WHEN mr.overall_point_won  = 0.0 THEN 1 ELSE 0 END) AS losses
```
This assumes `overall_point_won` is always a `{0, 0.5, 1}` match-outcome flag. For a Classical Stroke Play player, `overall_point_won` is instead a raw points value — **any positive value (+0.5 or more) gets miscounted as a "win," any exactly-0.0 gets miscounted as a "loss," and any negative value (a below-par-relative-but-negative-points week, or any non-0.5 fractional value) falls through all three buckets uncounted** — `wins + ties + losses` won't even equal `rounds_played` for these players. This is live on the `/standings/individual` page **today**, for any league actually using Classical Stroke Play — not a hypothetical.

The same page's Role column (`individual.html:113`) also renders the literal string `"FIELD"` as a role chip, styled identically to the real `A`/`B` team-position chips used by every other format — confusing, since `FIELD` isn't a team position at all.

## Design

Two independent pieces:

### 1. Fix the standings/individual W-L-T bug (small, isolated)

`scoring_mode` lives on `league_settings` per season (`schema_postgres.sql:141`) — a season is entirely one format, never mixed. So `standings.individual()` can check the season's mode once and branch:

- If `scoring_mode == 'classical_stroke_play'`: skip the wins/ties/losses `CASE` aggregation entirely for this season (or compute it from a season-wide rank comparison — see leaderboard below, which is the more meaningful stat anyway) — replace the Role/W-L-T columns with the season's actual meaningful stats for this format (points, rank).
- Every other mode: completely unchanged — this is purely an additive branch, no risk to existing match_play/stableford/best_ball/team_totals output.

### 2. A dedicated field-wide leaderboard (new, additive)

A real stroke-play format is a *ranking*, not a pairwise record — the natural display is "leaderboard," not "W-L-T." Model this after the already-shipped `stats.leaderboard()` (`GET /stats/leaderboard`, ranked-by-scoring-average, `Plans/2026-07-10-leaderboard-and-comparison-technical-spec.md`) rather than inventing new structure:

- New route, e.g. `GET /standings/<season_id>/classical-stroke-play` (or fold into `standings.individual()` as a mode-gated alternate template — see Open Question 1): rank every player by cumulative `total_points` across all completed weeks (season-to-date leaderboard), plus a per-week breakdown (week, net total, par, points that week) — mirrors what `compute_classical_stroke_play_points()` already computes per week, just aggregated and displayed instead of only feeding team standings silently.
- Reuses the existing `match_results` rows directly (`WHERE role = 'FIELD'`) — no new schema, no new computation, purely a read/display layer on data that already exists.
- Team affiliation still shown (each field player belongs to a team, `team_id` is already on the row) so the page can cross-reference "this is also feeding your team's regular standings" — avoids the page reading as disconnected from team standings.

## Open Questions for @user

1. **Where should this live?** (a) Gate `/standings/individual`'s existing template to show a different column set when the season's `scoring_mode` is Classical Stroke Play (reuses the existing page/nav entry, less new surface), or (b) a wholly separate page/route dedicated to it (cleaner separation, but one more nav entry). Recommend (a) — it's the same underlying question ("how did each individual player do this season"), just answered differently depending on format, matching how the page already varies its meaning by role/team context.
2. **Per-week breakdown**: worth showing week-by-week points (like GLT's field-position stroke-play pages do), or is a season-cumulative leaderboard enough? Recommend cumulative-only for v1 — per-week detail can reuse the existing per-round hole-by-hole scoring-detail page (`players.profile()`) if a specific week's detail is wanted, rather than duplicating it here.
3. Should the W-L-T bug fix (piece 1) ship independently and immediately, ahead of the leaderboard (piece 2)? It's a real, live-today correctness bug affecting any Classical Stroke Play league's `/standings/individual` page, and is small/isolated — recommend fixing it as its own quick patch regardless of when/whether the leaderboard is built.

## Critical Files

- `app/routes/standings.py:1058-1092` (`individual()` — bug + branch point)
- `app/templates/standings/individual.html:88, 113, 118` (Role chip + W-L-T display)
- `app/routes/scores.py:253-308` (`compute_classical_stroke_play_points()` — data source, unchanged)
- `app/routes/stats.py` (`leaderboard()` — pattern to mirror for the new ranked view)

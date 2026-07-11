# Individual All-Play — Technical Spec

**Status:** Decision: new tab in the standings sub-nav (2026-07-10, @user: "In the tab list on standings") — Built & shipped 2026-07-10. New route `standings.allplay_individual` (`GET /standings/<season_id>/allplay/individual`), new template `allplay_individual.html`, subnav link added to all 10 existing standings templates (the subnav is duplicated raw HTML, not a shared include — confirmed and accepted as the known cost of this placement choice). Found and fixed 2 pre-existing Postgres GROUP BY/HAVING bugs in `standings.awards()` while validating (both unrelated to this feature, caught because the awards page 500'd during the sub-nav round-trip check). Validated: all 10 pages render 200 with the new tab present; round-robin win/loss/tie math for week 19 hand-verified against the real match_results data already validated earlier this session for the Match Play points fix.
**Type:** Technical Spec
**Linked WP:** New idea from @user, 2026-07-10 — extends an existing BGLT feature (Team All-Play), not a GLT parity item.
**Prepared by:** Claude, 2026-07-10

## Context

BGLT already has a **Team All-Play** page (`GET /standings/<season_id>/allplay`, `standings.py:929-1049`): for every completed week, every team's total points that week is compared pairwise against every *other* team's points that week (round-robin, not just their actual scheduled opponent), producing a hypothetical season-long W-L-T record — "if your team had played every other team every week instead of just your scheduled matchup, how would you have done." This is a standard fantasy-league concept for separating true performance from schedule luck, and it's also already reused internally as one of BGLT's tiebreaker priorities (`_tb_allplay_pct`, `standings.py:234`).

@user asked for the **individual player** version of the same idea: each player's own weekly result compared pairwise against every other player in the league that week, not just their actual match-play opponent.

## Design

### What to compare, per player, per week

`match_results` already stores one row per player per matchup with `total_points` (hole points + overall point, or the Classical Stroke Play field-wide points) — the exact per-player, per-week, opponent-independent number the team version already uses at the team level (`SUM(mr.total_points)` per team per week). The individual version is the identical mechanism, one level down: group by `player_id` instead of `team_id`, and everything else — the round-robin pairwise comparison, the W-L-T tally, the running win%, the per-week breakdown columns — carries over unchanged from `allplay()`'s existing logic. No new schema, no new computation of the underlying points; just a different `GROUP BY`.

### A note on Best Ball / Team Totals modes

In those two formats, both teammates share one combined result (`aa = bb = combined_result`, `scores.py`) — so an individual player's `total_points` is identical to their teammate's every week. Individual All-Play under those formats will show both teammates with identical W-L-T records that mirror their team's own All-Play record one-for-one — not a bug, just an accurate reflection of how those formats work (a team's performance *is* each player's performance when scores are combined before comparison). This naturally differentiates from match_play/stableford/Classical Stroke Play, where individual points genuinely diverge from a teammate's and the two views tell different stories. Worth a one-line note on the page itself so it doesn't read as broken the first time someone sees two identical rows.

### Placement

The existing Standings section has ~10 sub-pages (Standings, Team/Weekly Scorecards, All-Play, Individual, Flight, Trend, Awards, Playoff Picture) sharing one sub-nav bar — but that bar is **duplicated raw HTML in every template, not a shared include/macro**, so adding a brand-new top-level tab means touching all ~10 files just for the nav bar.

Two options:
1. **(Recommended) A toggle on the existing All-Play page** (e.g. "Team" / "Individual" pills at the top of `standings/allplay.html`, same route with a `?view=individual` query param or a second URL segment) — one file touched for the toggle, no subnav duplication cost, and it sits exactly where someone already comparing all-play records would look for the individual version.
2. **A new top-level route + subnav tab** (e.g. `standings.allplay_individual`) — cleaner URL, but means editing the sub-nav block in all ~10 standings templates to add the new link, for a page whose relationship to the existing All-Play page is "same concept, different grouping," not a genuinely separate concern.

### Table shape

Same shape as the existing team version, one row per player instead of per team: Player name, Team (for context), W-L-T, win %, season points (reference column), and the same per-week W-L-T breakdown columns already built for the team version. Default sort: win % descending, same tiebreak-by-wins convention already used (`allplay_rows.sort(key=lambda r: (-r['pct'], -(r['w'] + 0.5*r['t'])))`).

## Open Questions for @user

1. **Placement:** toggle on the existing All-Play page (recommended, avoids the ~10-file subnav-duplication cost) or a genuinely new route + subnav tab?
2. Any interest in also **cross-filtering** by division/flight (if the league uses them), matching how other standings pages already offer a Flight view — or keep this to a single league-wide table for v1?

## Critical Files

- `app/routes/standings.py:929-1049` (`allplay()` — the exact mechanism to generalize from team_id to player_id)
- `app/templates/standings/allplay.html` (existing table to extend with a toggle, or model a new template after)
- `app/routes/scores.py` (`compute_team_combined_result` — confirms why Best Ball/Team Totals teammates will show identical rows, no changes needed there)

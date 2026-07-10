# Technical Spec: Unified Contest Winners Report + Season Leaderboards

*Status: `Ready to build` — nav/naming resolved 2026-07-10: mirror GLT's own page names, not invented ones.*
*Decision doc this spec implements: `Plans/2026-07-09-contests-report-and-leaderboards.md`*

-----

## Goal

Four related, small reports, all reusing the same season/all-time scoping pattern and the same `contests`/`contest_results` schema already shipped in the Contests redesign (2026-07-09):

1. Unified cross-contest report — flat, filterable log of every contest result.
2. Per-player total $ won across all contests.
3. Season-long "Low Score winners by week" log.
4. Season skins leaderboard.

Every one of these needs to support **both** season-scoped and all-time views, per @user's 2026-07-10 resolution of the original open question.

**Naming/structure, per @user 2026-07-10**: mirror GLT's own page structure exactly rather than merging things into invented groupings. GLT ships these as 4 distinct pages under Contests, and BGLT should too — as 4 named tabs on one Contests-area report, not one page with a toggle:
- **"Contest Winner Detail"** — item #1, the flat filterable log.
- **"Summary"** — item #2, the per-player $-won leaderboard.
- **"Low Score"** — item #3, the weekly low-net/low-gross log (GLT's `individual-low-score`).
- **"Skins Leader"** — item #4, the season skins leaderboard (GLT's `individual-skins-leader`).

All 4 live under the Contests nav section (confirmed correct per GLT's own URL structure — all four are `contests/...` pages despite two carrying an `individual-` prefix in their slug).

## Shared scoping pattern

One convention used across all 4 reports: `season_id` query param, `None`/absent = all-time (spans every season for the league, not just the current one). This mirrors the existing `all_seasons` picker pattern already used throughout `stats.py`/`standings.py`, with one added "All-time" option at the top of the dropdown rather than a season being mandatory.

```python
season_id = request.args.get('season_id', type=int)  # None = all-time
season_filter_sql = "AND s.season_id = %(season_id)s" if season_id else ""
```

Every query below is written against **all** of a league's contests by default, filtered down to one season when `season_id` is provided — not the other way around (avoids two separate query paths per report).

## 1. Contest Winner Detail

**Route:** `GET /contests/winners` (tab: "Contest Winner Detail") — standalone read-only report, kept separate from `admin_edit.html`'s per-contest editing view, per the decision doc's Approach A.

Reuses `season_view()`'s existing per-contest result query (`contests.py:73-85`) almost exactly, just without the `WHERE cr.contest_id = %s` filter — instead scoped by season (or all seasons) and joined through `contests` to reach `season_id`:

```sql
SELECT c.name AS contest_name, c.contest_type, c.season_id, s.season_name,
       cr.week_num, cr.hole_number, cr.distance, cr.amount_won, cr.notes, cr.value_text,
       p.first_name, p.last_name, t.team_name,
       tp1.first_name AS t_p1_first, tp1.last_name AS t_p1_last,
       tp2.first_name AS t_p2_first, tp2.last_name AS t_p2_last
  FROM contest_results cr
  JOIN contests c ON cr.contest_id = c.contest_id
  JOIN seasons  s ON c.season_id   = s.season_id
  LEFT JOIN players p   ON p.player_id = cr.player_id
  LEFT JOIN teams t     ON t.team_id   = cr.team_id
  LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
  LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
 WHERE c.league_id = %(league_id)s {season_filter_sql}
 ORDER BY s.season_id DESC, cr.week_num ASC NULLS FIRST, c.contest_id
```

Week/date/course context comes from `matchups` the same way `season_view()` already derives it (`contests.py:60-68`) — reused unchanged, just needs to run once per season present in the result set instead of once for a single season.

Filters (matching GLT's 4 dropdowns): Contest Type, Week, Player, Team — all applied client-side or as additional optional SQL predicates on the same query; no new query shape needed per filter, just optional `AND` clauses.

## 2. Summary (per-player $ won across contests)

**Route:** `GET /contests/winners/summary` (tab: "Summary"). Same query as #1, grouped instead of listed:

```sql
SELECT p.player_id, p.first_name, p.last_name, SUM(cr.amount_won) AS total_won
  FROM contest_results cr
  JOIN contests c ON cr.contest_id = c.contest_id
  JOIN players  p ON p.player_id   = cr.player_id
 WHERE c.league_id = %(league_id)s {season_filter_sql} AND cr.amount_won IS NOT NULL
 GROUP BY p.player_id, p.first_name, p.last_name
 ORDER BY total_won DESC
```

Team-scoped contests (`team_low_net`) won't have a `player_id` on their result rows — this summary is inherently player-only (matches GLT's page), team-based winnings just don't contribute here, which is correct, not a gap.

## 3. Low Score (season-long winners-by-week log)

**Route:** `GET /contests/winners/low-score` (tab: "Low Score").

**Design note:** this is the one report that's inherently season-scoped by nature (a week only exists within one season), so "all-time" here means "the log is queryable across every season the same way," not a single flattened cross-season view — matches the decision doc's own framing of this distinction.

Reuses the Weekly Recap's existing low-gross/low-net-per-week calculation logic (already built, `email_config.py`'s recap builder) rather than reimplementing it — that logic already correctly handles ties (standard competition ranking, all ties at the winning score included) per the 2026-07-09 Weekly Recap content-notes batch. Instead of only computing this on-demand for one week's recap email, this report runs it for **every completed week in the selected season** (or every week across every season for all-time) and persists nothing new — computed fresh per request, same as the recap does, since the underlying `hole_scores`/`scorecards` data doesn't change after a round is scored (no staleness risk from not caching it).

## 4. Skins Leader (season skins leaderboard)

**Route:** `GET /contests/winners/skins` (tab: "Skins Leader").

```sql
SELECT sr.winner_player_id, p.first_name, p.last_name,
       COUNT(*) AS skins_won, SUM(sr.payout) AS total_won
  FROM skins_results sr
  JOIN rounds   r ON sr.round_id    = r.round_id
  JOIN matchups m ON r.matchup_id   = m.matchup_id
  JOIN seasons  s ON m.season_id    = s.season_id
  JOIN players  p ON sr.winner_player_id = p.player_id
 WHERE s.league_id = %(league_id)s {season_filter_sql} AND sr.winner_player_id IS NOT NULL
 GROUP BY sr.winner_player_id, p.first_name, p.last_name
 ORDER BY skins_won DESC
```

`carried_over` skins (rows where no winner was determined that hole, `winner_player_id IS NULL`) are correctly excluded via the `IS NOT NULL` filter — they're not a player's win, just a rollover marker. "Owed/Paid" status (a GLT column) isn't tracked anywhere in BGLT's `skins_results` schema today — flagging this as a real gap this spec doesn't close, not silently dropped: if payment tracking matters, that's a separate small schema addition (`skins_results.paid BOOLEAN`), not bundled into this report build.

## Effort: S–M overall. No schema changes needed for #1/#2/#4 (reuse existing tables); #3 reuses existing calculation code, no new query logic. One new route file section (or additions to `contests.py`), one shared sub-nav (4 tabs: Contest Winner Detail / Summary / Low Score / Skins Leader) with 4 templates behind it, matching GLT's own page split rather than merging any of them.

## Testing plan

Validate against real dev Postgres for both season-scoped and all-time views: confirm the all-time view actually spans every season present in dev data (not just the current one), confirm filters (#1) narrow results correctly, confirm the skins leaderboard excludes carried-over rows, confirm the low-score log's tie-handling matches the Weekly Recap's own output for a week already validated there.

## Next step

Ready to build — no remaining open questions.

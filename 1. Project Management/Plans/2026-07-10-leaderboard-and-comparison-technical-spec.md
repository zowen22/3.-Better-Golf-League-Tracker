# Technical Spec: League Scoring Leaderboard + Player Season Comparison

*Status: `Ready to build` — both decisions confirmed 2026-07-10, spec grounded directly in `stats.py`/`players.py`.*
*Decision docs this spec implements: `Plans/2026-07-09-league-scoring-leaderboard.md`, `Plans/2026-07-09-player-season-comparison.md`*

-----

## Goals

Two small, independent additions to `stats.py` — no shared code between them beyond the blueprint they live in. Bundled into one spec because both are the same *shape* of work: read stats that already exist per-player-per-season somewhere in the codebase, and re-present them ranked (Leaderboard) or side-by-side (Comparison). Neither needs new domain logic or schema.

## 1. League Scoring Leaderboard

**Route:** `stats.leaderboard` → `GET /stats/leaderboard` (standalone page, per @user's decision — not a tab on `/hole-averages`).

### Current state (grounded in the actual code)

`stats.py`'s `hole_averages()` (lines 200–351) already computes, for **one selected player** in **one selected season**: per-hole `avg_score`, `rounds`, and eagle/birdie/par/bogey/double/other counts + percentages (lines 258–295), via a single query grouped by `hs.hole_number, h.par`. The same function also computes a **league-wide, all-players-combined** version of the same query for hole-difficulty ranking (lines 298–342) — but that collapses all players into one number per hole; it does not rank players against each other.

There is no query anywhere that runs this per-player calculation for *every* player in a season and sorts the result — that's the entire gap.

### Design

New query, parameterized by `season_id` only (no `player_id` filter), grouped by player instead of collapsed across all players:

```sql
SELECT sc.player_id, p.first_name || ' ' || p.last_name AS player_name,
       COUNT(DISTINCT sc.scorecard_id) AS rounds,
       ROUND(AVG(hs.gross_score), 2)   AS avg_gross_per_hole,
       ROUND(SUM(hs.gross_score) * 1.0 / COUNT(DISTINCT sc.scorecard_id), 2) AS avg_gross_per_round
  FROM hole_scores hs
  JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
  JOIN rounds r       ON sc.round_id     = r.round_id
  JOIN matchups m     ON r.matchup_id    = m.matchup_id
  JOIN players p      ON sc.player_id    = p.player_id
 WHERE m.season_id = %s AND m.is_bye = 0 AND sc.is_absent = 0
 GROUP BY sc.player_id, p.first_name, p.last_name
 ORDER BY avg_gross_per_round ASC
```

This is structurally the same query as `hole_averages()`'s existing per-player block, just grouped by `player_id` instead of filtered to one, and rolled up to a per-round average for ranking (hole-by-hole detail is supporting columns, not the sort key — matches GLT's own layout: ranked by scoring average, hole-by-hole shown alongside).

For the hole-by-hole columns (1–9, matching GLT), reuse the *exact* existing per-player query from `hole_averages()` (lines 258–280) in a loop over the ranked player list — same pattern already proven correct, not reimplemented. At typical league roster sizes (10–30 players) this is a trivial N+1, not worth optimizing into one giant pivoted query.

### Route sketch

```python
@bp.route('/leaderboard')
@login_required
def leaderboard():
    db = get_db()
    league_id = session['league_id']
    season_id = request.args.get('season_id', type=int) or session.get('current_season_id')
    # ... season list + season row lookup, same pattern as hole_averages()

    ranked = db.execute(<leaderboard query above>, (season_id,)).fetchall()

    # Per-player hole-by-hole detail, reusing hole_averages()'s existing per-player query
    leaderboard_rows = []
    for rank, row in enumerate(ranked, 1):
        player_holes = <existing per-player hole query>(season_id, row['player_id'])
        leaderboard_rows.append({'rank': rank, **dict(row), 'holes': player_holes})

    return render_template('stats/leaderboard.html', all_seasons=..., season=..., leaderboard_rows=leaderboard_rows)
```

Worth factoring the existing per-player hole query out of `hole_averages()` into a small shared helper (`_player_hole_averages(db, season_id, player_id)`) so both routes call one implementation instead of two copies drifting — same discipline as this session's Phase 0 scoring-engine consolidation.

### New template

`templates/stats/leaderboard.html` — season picker (same pattern as `hole_averages.html`), ranked table: Pos, Player, Rounds, hole-by-hole 1–9, Gross Avg (Out/In/Total to match GLT if 18-hole, or just per-round total for 9-hole leagues). Nav link added under Stats & Records.

### Effort: S. No schema, no migration, one new route + one new template, reuses proven query logic.

-----

## 2. Player Season Comparison

**Route:** `stats.player_compare` → `GET /stats/player-compare` (standalone page — separate from the existing team-level `/compare`, per the "Current BGLT state" analysis in the decision doc: `/compare`'s season_rows loop is team/league-scoped and would need real surgery to also carry a per-player dimension; cleaner as its own route reusing the same season-picker UI pattern).

**Stats to compare** (confirmed by @user): **gross average**, **net average**, **handicap average** — for one player, across two selected seasons. Not included: points, W-T-L (the decision doc had floated these as options; @user narrowed to just the three scoring/handicap stats).

### Current state (grounded in the actual code)

`players.py`'s `profile()` already builds a `season_list` (lines 187–213) — one row per season this player has played, with `rounds`, `total_pts`, `avg_gross`, `best_gross`. Two of the three needed stats are **not** in this structure yet:
- **`avg_gross` already exists** per season (line 211) — reuse directly.
- **`avg_net` does not exist per season** — `round_data` computes `net_total` per individual round (line 158, via summing `hole_scores.net_score`) but the `season_map`/`season_list` aggregation loop (lines 188–213) never carries `net_total` into the per-season rollup, only `gross`. This needs one small addition: append `net_total` into `season_map[sid]` alongside the existing `gross` list, same pattern.
- **`avg_handicap` does not exist per season at all** — nothing in `profile()` aggregates handicap by season. The closest existing data is `sc.handicap_at_time_of_play` (already selected into `round_data` as `hcp_used`, line 122/169) — the playing handicap actually used for each round. Averaging `hcp_used` across a season's rounds (same aggregation shape as gross/net) gives "average handicap this player played on this season" — the natural reading of GLT's "handicap before/after" comparison, and consistent with data already computed elsewhere (no new query against `handicap_history` needed).

### Design

This doesn't need a new page built from scratch — it needs a **new route** that reuses `profile()`'s existing round-fetch query (lines 112–144) filtered to one player, extends the season aggregation to include `avg_net` and `avg_hcp` (two new accumulator lists alongside the existing `gross` list), then picks out just the two selected seasons' rows and computes deltas.

```python
@bp.route('/player-compare')
@login_required
def player_compare():
    db = get_db()
    league_id = session['league_id']

    players = db.execute("SELECT player_id, first_name || ' ' || last_name AS name FROM players "
                          "WHERE league_id = %s ORDER BY last_name, first_name", (league_id,)).fetchall()
    seasons = db.execute("SELECT season_id, season_name FROM seasons WHERE league_id = %s "
                          "ORDER BY season_id DESC", (league_id,)).fetchall()

    player_id  = request.args.get('player_id', type=int)
    season_a_id = request.args.get('season_a', type=int)
    season_b_id = request.args.get('season_b', type=int)

    comparison = None
    if player_id and season_a_id and season_b_id:
        season_stats = _player_season_stats(db, player_id, league_id)  # {season_id: {avg_gross, avg_net, avg_hcp, rounds}}
        a, b = season_stats.get(season_a_id), season_stats.get(season_b_id)
        if a and b:
            comparison = {
                'avg_gross': _delta(a['avg_gross'], b['avg_gross']),
                'avg_net':   _delta(a['avg_net'],   b['avg_net']),
                'avg_hcp':   _delta(a['avg_hcp'],   b['avg_hcp']),
            }

    return render_template('stats/player_compare.html', players=players, seasons=seasons, comparison=comparison, ...)
```

`_player_season_stats(db, player_id, league_id)` — new small helper, structurally a trimmed copy of `profile()`'s round-fetch + season-aggregation logic (lines 112–213), but only computing the 3 needed averages instead of everything the full profile page needs (hole-by-hole history, nicknames, sparkline, etc. are irrelevant here). Not extracted as a shared function with `profile()` itself since `profile()`'s version does meaningfully more (career totals, hole-by-hole) — duplicating the ~15-line aggregation loop is simpler and lower-risk than threading an extra "compute mode" flag through the existing profile route.

`_delta(val_a, val_b)` — small helper returning `{a, b, amount_change, pct_change}`, handling `None` gracefully (player didn't play that season) — mirrors GLT's Value/Amount Change/% Change columns.

### New template

`templates/stats/player_compare.html` — player picker + two season pickers, submit shows a 3-row table (Gross Average / Net Average / Handicap Average) × (Season A value, Season B value, Amount Change, % Change). Nav link added under Stats & Records, next to the Leaderboard link above.

### Effort: S–M. No schema, no migration. One new route, one small new aggregation helper (not a full profile-page duplicate), one new template.

-----

## Testing plan

Same pattern as every build this session: validate against real dev Postgres, not just logic review.
- **Leaderboard**: for the same season already used in the Phase 1 scoring-format validation, hand-verify the top 2-3 ranked players' `avg_gross_per_round` against a manual sum/count from `hole_scores`, confirm ranking order and hole-by-hole columns match `hole_averages()`'s existing single-player output for at least one of those players (proves the shared query logic wasn't altered).
- **Player Comparison**: pick a player with rounds in 2+ seasons (if the dev DB only has one season, this needs a second synthetic season or an accepted single-season smoke test of the "not enough data" path), hand-compute gross/net/handicap averages for each season from raw `hole_scores`/`scorecards`, compare against the route's output.

## Next step

Both ready to build — no remaining open questions. Recommend building in the same pass since they touch the same file (`stats.py`) and nav section (Stats & Records).

# Technical Spec: Player Participation / Attendance Report

*Status: `Ready to build` — @user 2026-07-10: visible to all members (not admin-only).*
*Decision doc this spec implements: `Plans/2026-07-09-player-participation-report.md`*

-----

## Goal

Season attendance summary per player: Rounds Scheduled, Rounds Played, Participation %, Sub Count, Absent Count — matching GLT's `individual/player-participation`. Pure aggregation over tables that already exist; no new schema.

## Grounded in the actual schema

- `matchups` (`season_id`, `team1_id`, `team2_id`, `is_bye`, `week_number`) — a matchup is "scheduled" for a player if their team is `team1_id` or `team2_id` and `is_bye = 0`.
- `teams` (`player1_id`, `player2_id`) — resolves which player_ids belong to a matchup's two teams.
- `scorecards` (`round_id`, `player_id`, `is_absent`) — a round is "played" by a player if a scorecard exists for them with `is_absent = 0`.
- `player_absences` (`round_id`, `player_id`, `sub_player_id`, `excused`, `matchup_id`) — one row per absence. `sub_player_id IS NOT NULL` means a sub covered; `NULL` means ghost-scored, no sub.

## Design

One query per league/season, grouped by player:

```sql
WITH player_teams AS (
    SELECT player1_id AS player_id, team_id FROM teams WHERE season_id = %s AND league_id = %s
    UNION ALL
    SELECT player2_id AS player_id, team_id FROM teams WHERE season_id = %s AND league_id = %s
),
scheduled AS (
    SELECT pt.player_id, COUNT(*) AS rounds_scheduled
      FROM player_teams pt
      JOIN matchups m ON (m.team1_id = pt.team_id OR m.team2_id = pt.team_id)
     WHERE m.season_id = %s AND m.is_bye = 0
     GROUP BY pt.player_id
),
played AS (
    SELECT sc.player_id, COUNT(*) AS rounds_played
      FROM scorecards sc
      JOIN rounds r   ON sc.round_id  = r.round_id
      JOIN matchups m ON r.matchup_id = m.matchup_id
     WHERE m.season_id = %s AND m.is_bye = 0 AND sc.is_absent = 0
     GROUP BY sc.player_id
),
absences AS (
    SELECT pa.player_id,
           COUNT(*) AS absent_count,
           SUM(CASE WHEN pa.sub_player_id IS NOT NULL THEN 1 ELSE 0 END) AS sub_count
      FROM player_absences pa
      JOIN matchups m ON pa.matchup_id = m.matchup_id
     WHERE m.season_id = %s
     GROUP BY pa.player_id
)
SELECT p.player_id, p.first_name, p.last_name,
       COALESCE(s.rounds_scheduled, 0) AS rounds_scheduled,
       COALESCE(pl.rounds_played, 0)   AS rounds_played,
       COALESCE(a.absent_count, 0)     AS absent_count,
       COALESCE(a.sub_count, 0)        AS sub_count
  FROM players p
  LEFT JOIN scheduled s  ON s.player_id  = p.player_id
  LEFT JOIN played    pl ON pl.player_id = p.player_id
  LEFT JOIN absences  a  ON a.player_id  = p.player_id
 WHERE p.league_id = %s
 ORDER BY p.last_name, p.first_name
```

`player_teams` (the `UNION ALL` CTE) is needed because `teams` stores two player_ids per row, not one row per player — every other per-player aggregation in this codebase (`profile()`, `hole_averages()`) sidesteps this by joining through `scorecards` instead (which already has one row per player per round), but "scheduled" specifically needs to count matchups **regardless of whether a scorecard was ever created** (a never-played, never-subbed absence still needs to count as scheduled) — `scorecards` alone would undercount a player who was scheduled but has zero rows for that round in some edge case. `player_teams` is the one new pattern this report needs; not reusable from elsewhere.

**Participation % = `rounds_played / rounds_scheduled * 100`**, computed in Python (not SQL) to cleanly handle `rounds_scheduled = 0` (new/inactive players) without a DB-side division-by-zero guard.

## Route

`GET /stats/participation` (visible to all members, per @user's decision — no `@admin_required`, just the existing `@login_required` pattern every other Stats page uses). Season picker (same pattern as `hole_averages()`/`leaderboard()`), one table: Player, Rounds Scheduled, Rounds Played, Participation %, Sub Count, Absent Count, sorted by Participation % ascending by default (lowest attendance first — the actually useful sort order for a commissioner scanning for reliability issues, even though this is member-visible now rather than admin-only).

## Effort: S. No schema, no migration — one new route with one CTE-based query, one new template. Nav link under Stats & Records.

## Testing plan

Validate against real dev Postgres: for a player with at least one absence (with and without a sub) in the existing seeded data, hand-count scheduled matchups, played rounds, sub/absent counts directly against `matchups`/`scorecards`/`player_absences`, compare to the route's output. Specifically verify a player scheduled but fully ghost-scored (absent, no sub) still shows the correct `rounds_scheduled` (this is the case `player_teams` exists to get right).

## Next step

Ready to build — no remaining open questions.

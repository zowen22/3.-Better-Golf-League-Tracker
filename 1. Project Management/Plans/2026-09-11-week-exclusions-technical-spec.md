# Technical Spec: Week Exclusions (Stats / Handicap / Points, Independently)

*Status: `Built & shipped` — 2026-09-12, per @user's "go ahead" on the full build (all 4 phases in one session, not phased across multiple). Owner: @claude. Requested by @user 2026-09-11: "a way to exclude weeks from being included in Player Stats, Handicap calculation, and point calculation — all separately." All 5 open questions resolved 2026-09-12 (see Decisions Log in `2. Project Overview.md`) and built the same day. See Work Packages WP3.32 for the full shipped-shape writeup, including the two real gaps closed along the way (migration registration ordering relative to `valid_round_gross`, and `recalc_handicap_for_player`'s pre-existing missing `matchups` join). Verified live against real dev Postgres with real scored data: all 3 flags toggled independently and cross-checked against each other, not just individually.*

## Goal

Let an admin mark a specific week as excluded from any combination of three independent concerns:

1. **Player Stats** — leaderboards, Hall of Fame/Records, player profiles/scoring history, Contest Winners, player comparisons.
2. **Handicap calculation** — a player's handicap index shouldn't move based on that week's rounds.
3. **Points / standings** — the week's matches shouldn't count toward W-L-T, points totals, or any tiebreaker.

These need to be **fully independent toggles**, not one on/off switch — the motivating case is a fun-format/scramble week (scores worth keeping visible in stats, but shouldn't touch handicaps or points), as well as the opposite case (a rained-out/voided week that should vanish from everything). A single week may have any combination of the three set.

## Why this is a bigger surface than it looks

There is **no existing per-concern exclusion mechanism anywhere in the app today.** `matchups.week_type` (`Normal`/`Rain Out`/`League Bye`/etc.) looks like it might already do this — it doesn't. Grepped every stats/handicap/standings query file: `week_type` is read only by `schedule.py`, `admin.py`, `display.py`, `public_view.py`, and `reports.py` — purely for display/scheduling UI. It is never checked by `stats.py`, `records.py`, `handicap.py`, `standings.py`, `contests.py`, or `players.py`. So this is new plumbing, not a matter of wiring up a flag that's already half-there.

Three research passes (one per concern, against the real codebase) found **~70 distinct query functions across 6 files** that would each need a new filter added. That size is exactly why this task's output is a spec, not code — the same "spec first, build on explicit go-ahead" pattern this project already used for `point_overrides` (`2026-08-09-points-override-technical-spec.md`).

## Existing precedents worth reusing

- **`archive_settings.locked`** (`routes/archive.py`) — one row per season, `season_is_locked(db, season_id, league_id)` + `block_if_locked(db, season_id, league_id, redirect_endpoint, **kwargs)` called at the top of every points/handicap-mutating route (6 sites in `scores.py`, plus `schedule.py`, `admin.py`, `handicap.py`). This is the closest architectural precedent for "a small opt-in-row flag plus a shared guard function checked at write sites" — this spec's helper module should mirror its shape, just scoped to `(season_id, week_number)` instead of `season_id` alone, and needing three independent booleans instead of one.
- **`scorecards.is_absent`** — the closest precedent for "this round doesn't count toward handicap." When a player is absent with no sub, a ghost gross score is synthesized (so match points/net scores still compute normally for that week) and the scorecard is flagged `is_absent=1`; every handicap-differential query then filters `AND sc.is_absent = 0`. Notably, **the round still counts for points/standings** — only the handicap-differential pool excludes it. This is direct precedent for "one concern excludes a round, a different concern doesn't" being normal, expected behavior in this codebase already, not a new idea being introduced.
- **`point_overrides` + `apply_point_overrides()`** (`scores.py:320`) — a single function called at all 9 real `match_results` write sites, right before `db.commit()`. Good precedent for a *write-time* choke point, but standings/stats are computed *live* at read time (see below), so this pattern doesn't directly transfer to those two concerns — flagging so a future build doesn't try to force-fit it.
- **`valid_round_gross`** (view, `migrations/add_valid_round_gross_view.sql`) — already centralizes `is_absent=0 AND is_bye=0 AND status='completed'` and is reused by several `stats.py`/`records.py` queries. Extending this view once to also filter `exclude_stats` gets several call sites the filter "for free" without touching each individually.

## Data model

One new table, opt-in-row (no row for a week = nothing excluded), matching `archive_settings`'s convention of a real row only existing once something's actually been toggled:

```sql
CREATE TABLE week_exclusions (
    exclusion_id       SERIAL PRIMARY KEY,
    season_id           INTEGER NOT NULL REFERENCES seasons(season_id),
    week_number         INTEGER NOT NULL,
    exclude_stats       INTEGER NOT NULL DEFAULT 0,
    exclude_handicap    INTEGER NOT NULL DEFAULT 0,
    exclude_points      INTEGER NOT NULL DEFAULT 0,
    reason              TEXT,
    updated_by_user_id  INTEGER REFERENCES users(user_id),
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (season_id, week_number)
);
CREATE INDEX idx_week_exclusions_season_week ON week_exclusions(season_id, week_number);
```

(`INTEGER` 0/1 rather than `BOOLEAN`, matching this schema's existing convention — `matchups.is_bye`, `scorecards.is_absent`, `archive_settings.locked` are all `INTEGER`, not `BOOLEAN`, throughout `schema_postgres.sql`.)

**Deliberately week-level, not matchup-level.** A matchup-level flag would need to be set on every matchup row within that week individually — exactly the fragility this project already hit once this year: the 2026-09-05 bye-convention bug, where a newly-added matchup row silently missed a flag that existing rows already had, because nothing forced it to inherit the week's convention. A week-level row applies uniformly no matter how many matchup rows exist in that week, or get added to it later (e.g. via the existing "+ Add Matchup" action).

**Migration**: new `app/migrations/add_week_exclusions.sql`, registered in `init_db.py`'s `additive` list. (Per this project's own repeatedly-learned lesson, logged multiple times in Session Log/Technical Reference: "new columns/tables need THREE things — schema file, migration file, `init_db.py` registration" — a migration that ships unregistered has caused a live production 500 before.)

## Helper module — the one place every call site reads from

New `routes/week_exclusions.py`, mirroring `archive.py`'s shape:

```python
_KINDS = {'stats', 'handicap', 'points'}

def get_week_exclusion(db, season_id, week_number):
    """Returns the week_exclusions row, or None if the week has never been touched."""
    return db.execute(
        "SELECT * FROM week_exclusions WHERE season_id = %s AND week_number = %s",
        (season_id, week_number)
    ).fetchone()

def is_week_excluded(db, season_id, week_number, kind):
    assert kind in _KINDS
    row = get_week_exclusion(db, season_id, week_number)
    return bool(row and row[f'exclude_{kind}'])

def set_week_exclusion(db, season_id, week_number, *, exclude_stats, exclude_handicap,
                        exclude_points, reason, user_id):
    """Upsert — one row per (season_id, week_number), matching the UNIQUE constraint."""
    db.execute("""
        INSERT INTO week_exclusions
            (season_id, week_number, exclude_stats, exclude_handicap, exclude_points,
             reason, updated_by_user_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (season_id, week_number) DO UPDATE SET
            exclude_stats = EXCLUDED.exclude_stats,
            exclude_handicap = EXCLUDED.exclude_handicap,
            exclude_points = EXCLUDED.exclude_points,
            reason = EXCLUDED.reason,
            updated_by_user_id = EXCLUDED.updated_by_user_id,
            updated_at = CURRENT_TIMESTAMP
    """, (season_id, week_number, exclude_stats, exclude_handicap, exclude_points, reason, user_id))
```

Plus one SQL fragment constant per kind, so every one of the ~70 call sites below pulls from the same string instead of hand-typing a subquery seventy times and inevitably drifting:

```python
# Assumes the query's matchups table is aliased "m" -- true at every call site found below.
WEEK_EXCLUSION_FILTER = {
    kind: (
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM week_exclusions we WHERE we.season_id = m.season_id "
        f"AND we.week_number = m.week_number AND we.exclude_{kind} = 1)"
    )
    for kind in _KINDS
}
```

**Enforcement pattern: read-time filtering**, not a write-time hook. This matches the app's own established style — `is_bye = 0` and `status = 'completed'` are already copy-pasted as WHERE conditions at 60+ sites rather than centralized, so extending that exact convention is lower-risk than inventing new architecture. It's also the *only* option for Stats and Points, since neither is materialized (see below) — there's no "recompute" step to hook a write-time function into.

## Per-concern breakdown

### Points / Standings — simplest, do this one first

`match_results` is written at 9 sites (the same 9 `point_overrides` already hooks into — `scores.py`'s `_recalc_single_round`/`reopen_scores`/clear-scores path/`compute_classical_stroke_play_points`, `admin.py`'s `_save_edited_scores`, both `api.py` iOS paths, `self_report.py`'s approval flow, `score_import.py`), but standings themselves are **not materialized** — `season_standings` exists in the schema but has zero real read/write call sites anywhere in the app (dead table). Every standings page (`standings.py`) computes live via `SUM`/`COUNT` over `match_results JOIN matchups` at request time. That means:

- **No rebuild step needed** — a read-time filter takes effect on the very next page load.
- Add `WEEK_EXCLUSION_FILTER['points']` to `standings.py`'s ~15 functions, each independently aggregating `match_results`/`matchups`: `_standings_rows`, `divisions`, `scorecards`, `weekly`, `league_standings_detail`, `allplay`, `allplay_individual`, `individual`, `trend`, `awards`, `playoff_picture`, `flight_standings`, `get_standings_context`, and the 4 `_tb_*` tiebreaker helpers (`_tb_head_to_head`, `_tb_points_pct`, `_tb_allplay_pct`, `_tb_scoring_avg`).
- Bounded and independently testable end-to-end against real Postgres — recommend building this concern first, both because it's the smallest of the three and because it validates the whole `week_exclusions` plumbing (schema, helper, admin UI) before the harder handicap piece.

### Handicap — needs an extra step the other two don't

`handicap.py` has **two independent engines** that both read round history, and both would need the filter:

- **`rebuild_player_handicap_timeline()`** / **`rebuild_league_handicaps_and_scores()`** — the chronological, authoritative rebuild (runs automatically after every round save, and is the primary engine per the module's own docstring). Already joins `matchups` and filters `is_bye=0 AND status='completed'` — adding `WEEK_EXCLUSION_FILTER['handicap']` here is one query, in one place, since it recomputes the whole history in order every time it runs.
- **`recalc_handicap_for_player()`** — an older, incremental path used by `score_import.py`, `self_report.py`, API score endpoints, and the standalone "Recalc Handicaps" admin action. **This one currently has no `matchups` join at all** — a pre-existing gap found during this research, independent of this feature. Adding the exclusion filter here forces fixing that gap too (the join has to exist before the filter can be added to it) — a good side-effect, not scope creep, since otherwise this path would silently ignore the new exclusion flag entirely while the other engine honored it, producing two engines that disagree.

**The real wrinkle**: `handicap_history` is a *materialized* rebuild output, unlike standings/stats. Toggling `exclude_handicap` on a week that's already been played has **no visible effect until a rebuild runs** — same as any other retroactive handicap-affecting edit in this app. The three existing admin actions that already mutate handicap-affecting data (`matrix_update`, `clear_scorecard_overrides`, `clear_handicap_override`) all auto-trigger `rebuild_league_handicaps_and_scores()` immediately after saving — recommend the same behavior here rather than leaving the admin to remember to separately hit "Rebuild Handicap Timeline" afterward. The existing `/handicap/rebuild` route's preview/rollback safety net can be reused rather than building new rebuild-safety logic.

### Player Stats — largest surface, do this one last

No materialization here either (all fully live), but the widest raw call-site count:

- **`stats.py`** (7 functions) — `compare`, `_player_hole_averages` (shared by `hole_averages`/`leaderboard`), `hole_averages`, `leaderboard`, `_player_season_stats` (used by `player_compare`), `course_stats`, `participation`.
- **`records.py`** — Hall of Fame; one large function with multiple inline queries over `valid_round_gross`, `matchups`, `match_results`, `teams`.
- **`players.py`** (4+ functions) — `profile` (round history — worth double-checking this one specifically has no existing `is_bye`/`status` filter at all today, found during research, separate from this feature), `scoring_by_year`, `compare`, `handicap_detail`.
- **`contests.py`** (7+ functions) — `_build_season_contest_data`, `admin_list`, `admin_edit`, `_calculate_team_low_net_week`, `admin_calculate_all`, `winners_detail`, `winners_summary`, `winners_low_score`.

Extending **`valid_round_gross`** once (add `WEEK_EXCLUSION_FILTER['stats']`, translated into the view's own JOIN shape) covers every query that already reads through it — several of the `stats.py`/`records.py` functions above — for free, which meaningfully reduces the real number of individual edits below the raw ~50-60 function count. The remaining functions that build their own `hole_scores`/`scorecards`/`rounds`/`matchups` joins directly (not through the view) need the filter added by hand, one at a time.

## Admin UI — decided 2026-09-12

**Both the Schedule page and Score Entry's Edit Week Settings panel**, not just one. Same underlying `set_week_exclusion()` write and the same three checkboxes (Exclude from Stats / Exclude from Handicap / Exclude from Points) plus a reason field, surfaced in two places so it's reachable both from a season-wide review (Schedule page, next to the existing week-type chip — where `week_type`/`week_label` are already edited) and in the middle of a live entry session (Score Entry's existing "Edit Week Settings" disclosure, alongside Course/Side/Scheduled Date). Both POST to the same new admin-only, season-lock-gated route via `set_week_exclusion()` — no duplicated logic, just two entry points into the one helper.

**Visible badge wherever an excluded week appears** — decided over "stays visually identical." A week with any exclusion set gets a small badge (e.g. "Excluded from Points") on the Schedule page's week row, Score Entry's week header, and Weekly Recap, naming exactly which concern(s) are excluded. Purpose: nobody looking at a week's numbers should have to guess why they don't add up — the badge is the answer sitting right next to them, not just a checkbox state buried in an edit panel.

**No bulk "exclude everything" shortcut** — decided over adding one. Three independent checkboxes only, always. Keeps the UI honest about the three concerns genuinely being unrelated to each other — an admin ticks exactly what they mean, with nothing implying a default coupling that doesn't really exist in the data model.

## Handicap rebuild on toggle — decided 2026-09-12

**Silent auto-trigger**, matching the app's 3 existing precedents (`matrix_update`, `clear_scorecard_overrides`, `clear_handicap_override`) — toggling `exclude_handicap` calls `rebuild_league_handicaps_and_scores()` immediately after the `set_week_exclusion()` write, same as every other handicap-affecting admin edit in this app today. No separate preview/rollback confirmation step for this specific action (the existing `/handicap/rebuild` route's own preview/rollback UI is untouched and still available separately, for an admin who wants to double-check the effect before or after).

## Access scope — decided 2026-09-12

**League_admin-only, confirmed.** No member-facing surface anywhere in this feature — matches every other settings-mutation route in the app. Members only ever see the resulting badge on an excluded week, never a toggle.

## Effort

**M–L**, phased (recommended order — each phase is independently shippable and testable against real Postgres, per this project's standing validation convention):

1. Schema + migration + `week_exclusions.py` helper + Schedule-page admin UI. No behavior change yet — nothing reads the flags.
2. **Points** — ~15 `standings.py` functions get the filter. No rebuild step. Smallest, most bounded, validates the whole plumbing end-to-end first.
3. **Handicap** — both engines get the filter (closing `recalc_handicap_for_player`'s pre-existing missing-`matchups`-join gap as a necessary side effect), auto-rebuild wired on toggle.
4. **Stats** — largest surface; extend `valid_round_gross` first, then sweep the remaining `stats.py`/`records.py`/`players.py`/`contests.py` call sites not already covered by the view.

## Testing plan

Per phase, against real dev Postgres: create a week with a normal completed matchup, confirm baseline stats/handicap/points all include it; toggle one exclusion flag at a time and confirm *only* that concern's numbers change (the other two must be provably unaffected — this is the core requirement, "independently," so a test that only checks the toggled concern isn't sufficient); toggle it back off and confirm the week reappears everywhere; confirm a locked season blocks the new admin route the same as every other points/handicap-mutating route; for handicap specifically, confirm the rebuild actually ran and `handicap_history` reflects the exclusion, not just that the flag is set in the database.

## Next step

All 5 open questions resolved 2026-09-12 (see Admin UI, Handicap rebuild, and Access scope sections above). No code, schema, or migration changes made yet — needs an explicit "go ahead" (matching this project's `point_overrides` spec precedent) before Phase 1 begins.

# Technical Spec: Best Ball, Team Totals, High/Low, Classical Stroke Play

*Status: `Evaluating` — spec drafted 2026-07-10, needs @user sign-off on the schema/architecture below (and one genuine open question on High/Low's exact mechanic) before implementation starts.*
*Decision doc this spec implements: `Plans/2026-07-09-best-ball-format-question.md`*

-----

## Goals

Add 4 new scoring-format presets to BGLT — Best Ball, Team Totals, High/Low, and Classical Stroke Play — as fixed, non-combinable options selectable per league (alongside the existing Match Play and Stableford), per the decision doc. Settings surface should match GLT's own category list; presets are curated views over one shared settings library, not per-format duplicate tables.

## Current state (grounded in the actual code, not assumed)

- `league_settings.scoring_mode` (`schema_postgres.sql:141`) is a free-text column, currently only ever set to `'match_play'` or `'stableford'` — no CHECK constraint, so extending its valid values is a zero-migration-risk app-level change.
- **The match_play/stableford branch is implemented twice, independently**, in two different functions:
  - `_recalc_single_round()`'s inner `match_result()` (`scores.py:1026-1042`) — used when recalculating a round after the fact (e.g. handicap rebuild, score correction).
  - `_process_scores()`'s inner `match_result()` (`scores.py:1350-1368`) — used on live score submission.
  Both do the identical thing: if `stableford`, sum `calc_stableford()` per hole then compare totals via `calc_match_play()`; else call `diff_match_hole_points()` (handicap-differential hole-by-hole + absolute-net overall). **This duplication should be consolidated as part of this work**, not left as two copies that could drift — adding 4 more branches to both copies independently would double today's maintenance risk.
- `calc_match_play(score_a, score_b)` (`scores.py:78-84`) hardcodes win/tie/loss to `2.0/1.0/0.0`. The `match_play_points_per_hole` setting exists in the schema but is **dead** (confirmed in the 2026-07-04 settings audit) — never read anywhere. Parameterizing this function is needed for the new formats' settings-driven point values anyway, and **also fixes this pre-existing dead setting for free**.
- `calc_stableford(net_vs_par)` (`scores.py:133-144`) hardcodes a 5-tier point curve. Same dead-setting situation applies to Stableford's granular settings (documented in Part 1) — out of scope for *this* spec, flagged only for awareness.
- **BGLT's scoring model is currently rigidly individual**: `_recalc_matchup_scoring`/`_process_scores` both split each 2-player team into A/B by playing handicap (`team_ab()`/`designate()`), then compute **A-vs-A and B-vs-B independently** — there is no code path anywhere that combines two teammates' scores into one team score before comparison.
- `match_results` (`schema_postgres.sql:383-397`) is keyed by `(matchup_id, player_id)` with an `opponent_player_id` column — i.e. one row per player, framed as "this player vs that specific opponent." For team-combined formats, both teammates will get the **same** hole/overall points (since it's their shared team score being compared), but the schema doesn't need to change — `opponent_player_id` can point at either/both opposing players, or be left conceptually loose since it's not displayed as a strict 1:1 pairing for these formats.
- **Standings aggregation is completely format-agnostic already**: every points query in `standings.py` (confirmed: lines 122, 146, 201-202, 225-226, 245-246, 449, 590) is `SUM(mr.total_points) GROUP BY team_id` (or player_id) — it has zero opinion on *how* those points were computed. This significantly de-risks Best Ball/Team Totals/High-Low: once `match_results` rows are populated correctly, standings, playoffs, awards, and the Weekly Recap all keep working with **no changes**.

## Schema changes

```sql
-- Extend scoring_mode's valid values (no migration needed -- TEXT column,
-- no CHECK constraint). App-level validation only.
-- New values: 'best_ball', 'team_totals', 'high_low', 'classical_stroke_play'

-- New settings, one group per format, matching GLT's own category split
-- (Best Ball Points, Team Totals Points, per the Settings Parity audit).
-- Additive, idempotent, mirrors this project's existing migration style.
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS best_ball_points_per_hole   REAL NOT NULL DEFAULT 2.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS best_ball_tie_points        REAL NOT NULL DEFAULT 1.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS best_ball_overall_point     REAL NOT NULL DEFAULT 2.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS team_totals_points_per_hole REAL NOT NULL DEFAULT 2.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS team_totals_tie_points      REAL NOT NULL DEFAULT 1.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS team_totals_overall_point   REAL NOT NULL DEFAULT 2.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS high_low_points_per_hole    REAL NOT NULL DEFAULT 2.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS high_low_tie_points         REAL NOT NULL DEFAULT 1.0;
ALTER TABLE league_settings ADD COLUMN IF NOT EXISTS high_low_overall_point      REAL NOT NULL DEFAULT 2.0;
-- Classical Stroke Play's point-value columns are NOT included here --
-- @user explicitly deferred the exact values/sign convention. Adding
-- placeholder columns now would just be guessing; that migration comes
-- once the values are actually decided (see Deferred section below).

-- Fix the pre-existing dead setting while touching this code anyway --
-- calc_match_play() gets parameterized (see below), so Match Play's own
-- points-per-hole setting becomes live for the first time.
-- (match_play_points_per_hole already exists in schema_postgres.sql:111 -- no new column needed, just wiring it up.)
```

## Core architecture

### 1. Consolidate the duplicated match_result() logic first

Extract a single shared function (new, in `scores.py` or a new `scoring_engine.py`):

```python
def compute_match_result(scoring_mode, settings, gross_x, gross_y, holes_x,
                          ph_x, ph_y, net_x, net_y):
    """Single source of truth for match_play/stableford/best_ball/team_totals/
    high_low point computation -- replaces the two independent copies in
    _recalc_single_round and _process_scores."""
    ...
```

Both `_recalc_single_round()` and `_process_scores()` call this one function instead of each having their own inline `match_result()` closure. This is a **refactor with zero behavior change** for existing Match Play/Stableford leagues — should ship and be verified against real dev Postgres *before* adding any new format, so any regression is caught against a known-good baseline rather than conflated with new-format bugs.

### 2. Parameterize the point-award functions

```python
def calc_match_play(score_a, score_b, win_pts=2.0, tie_pts=1.0, loss_pts=0.0):
    if score_a < score_b:
        return win_pts, loss_pts
    elif score_b < score_a:
        return loss_pts, win_pts
    else:
        return tie_pts, tie_pts
```

Existing call sites keep working unchanged (defaults match current hardcoded behavior). New formats pass their own settings-driven values.

### 3. Team-score combination layer (new)

```python
def combine_team_hole_score(method, score_a, score_b):
    """Combine two teammates' single-hole scores into one team score.
    method: 'best_ball' | 'team_totals'. (high_low handled separately -- see Open Question.)
    Returns None if either input is None (hole not yet scored)."""
    if score_a is None or score_b is None:
        return None
    if method == 'best_ball':
        return min(score_a, score_b)
    if method == 'team_totals':
        return score_a + score_b
    raise ValueError(f'unknown team-score method: {method}')
```

For Best Ball and Team Totals: compute each team's per-hole combined score (net, using the same `net[]` values already computed today), then feed **both teams' combined-score sequences** through the *same* hole-by-hole comparison + `calc_match_play`/`calc_stableford` logic used today — reusing the point engine, not duplicating it. Both players on the team receive the identical resulting points (since they share one team score), written as two `match_results` rows same as today.

### 4. High/Low — open question, not yet spec'd

GLT's description ("High/low of each teammate") is ambiguous enough that I don't want to guess the exact mechanic and build it wrong. Two real, distinct golf formats go by similar names:

- **(a) Fixed-role**: one teammate always contributes their better score, the other always their worse, summed — but this is mathematically identical to Team Totals (sum of both), so it's unlikely to be what GLT means as a *separate* format.
- **(b) Two simultaneous point competitions per hole** (sometimes called "High-Low" or "2 Low 2 High" in real club play): on each hole, the **better** of the two teammates' scores is compared against the opposing team's better score for one point, AND separately the **worse** of the two teammates' scores is compared against the opposing team's worse score for a second point — so up to 2 points are available per hole instead of 1. This reading is architecturally distinct from both Best Ball (only compares the low balls) and Team Totals (unconditional sum), which matches GLT listing it as a third, separate option.

**Recommend (b)** since it's the only reading that's genuinely different from the other two formats already being built, but this needs @user confirmation before implementation — worth getting right given it changes the actual points math, not just a settings default.

### 5. Classical Stroke Play — the field-wide outlier

This doesn't fit the matchup-pair model at all: instead of "my team vs your team," every player/team in the whole week's field is ranked by score relative to par, and points are a direct, linear function of that relative-to-par number (not a finish-position rank, not a tiered curve — per @user's decision).

Proposed shape:
1. Players/teams still play in their normal scheduled pairings for tee-time/handicap/scorecard purposes — nothing changes about *how rounds are played or scored hole-by-hole*.
2. **After** normal net scoring is computed, a separate step queries **every scorecard for that week** (not just the two teams in one matchup) to determine each player's/team's total relative-to-par, and converts it directly to points (`points = par − total_score`, sign TBD per @user's deferral).
3. This step must run once per week across the whole field, not per-matchup — likely a new function (`compute_classical_stroke_play_points(db, season_id, week_number)`) called after all of that week's matchups are scored, rather than living inside the existing per-matchup `_process_scores`/`_recalc_single_round` flow.
4. `match_results` rows still get written per player (`total_points` = the computed value), keeping `opponent_player_id` conceptually meaningless for this format (field-wide, not paired) — leave it NULL for these rows. Standings aggregation needs no changes (confirmed above).
5. **Explicitly deferred, not designed here**: the exact points formula/sign, and whether it should be net-based, gross-based, or both (GLT's version does "both net and gross totals" — @user hasn't confirmed if Classical Stroke Play needs both or just one).

### 6. GLT's "Stroke Play vs the Field" (rank-based) — setting only, not a preset

Per @user's decision, this doesn't get built as a preset. If ever added, it would be a low-level setting available regardless of active preset — out of scope for this spec entirely; noted here only so it doesn't get accidentally conflated with Classical Stroke Play during implementation.

## Settings UI

New settings sub-sections needed (admin settings page): Best Ball Points, Team Totals Points, High/Low Points (pending the open question above) — each mirroring the existing Match Play Points section's shape (points per hole, tie points, overall-match point). Classical Stroke Play's settings section is deferred until its point values are decided.

## Rollout plan

1. **Phase 0**: consolidate the duplicated `match_result()` logic into one shared function, verify zero behavior change for existing Match Play/Stableford leagues against real dev Postgres data. Ship this alone first.
2. **Phase 1**: Best Ball + Team Totals (the two with unambiguous mechanics) — new settings, `combine_team_hole_score()`, wire into the consolidated function from Phase 0.
3. **Phase 2**: High/Low, once the open question above is resolved.
4. **Phase 3**: Classical Stroke Play — separate build given its field-wide model, once point values/sign are decided.

Each phase is independently shippable and testable — no reason to block Best Ball/Team Totals on High/Low's open question or Classical Stroke Play's deferred values.

## Testing plan (per this project's established pattern)

For each phase: validate against real dev Postgres, not just unit-level logic — create a test league/season with real scorecards, set `scoring_mode` to the new format, run scoring, and confirm `match_results`/standings match a hand-computed expectation. Phase 0's refactor specifically needs a before/after comparison run against existing real match-play and stableford data to prove zero regression.

## Open questions before implementation

1. **High/Low's exact mechanic** (Section 4 above) — recommend the "2 points per hole, low-ball and high-ball compared separately" reading, but needs confirmation.
2. **Classical Stroke Play's point formula and sign** — explicitly deferred by @user; needs an answer before Phase 3 can start (Phases 1-2 don't depend on this).
3. **Classical Stroke Play: net, gross, or both?** — GLT's version tracks both separately; unconfirmed whether this league wants one or both.
4. **Rollout scope**: build all phases in sequence in one continuous effort, or treat each phase as its own separately-scheduled session?

## Next step

Confirm the architecture above (especially Phase 0's refactor-first approach and the High/Low mechanic question) and I'll start with Phase 0 — the safest, purely-mechanical consolidation that de-risks everything after it.

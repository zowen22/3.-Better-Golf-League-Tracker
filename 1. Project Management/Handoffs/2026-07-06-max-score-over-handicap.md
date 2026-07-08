# Handoff: Wire up `max_score_over_handicap` (differential cap in handicap calc)

*Status: `Done`*
*Created: 2026-07-06 — Planner: Opus (this session)*
*Priority: `Medium` — Effort: `M`*
*Depends on: None*
*Parallel-safe: `Yes` — touches only `handicap.py` (+ optionally `setting_help.py`); disjoint from the Site Admin Dashboard handoff.*

-----

## Goal

Make the existing-but-dead `league_settings.max_score_over_handicap` setting actually do what its label promises: cap how far a single round's differential can exceed the player's handicap when that round feeds the handicap-index average. A blow-up round should stop over-inflating a player's index. After this, selecting a value in the admin settings form changes computed indexes (currently it changes nothing).

## Context

During the 2026-07-04 GLT parity audit, `max_score_over_handicap` was found to be one of five "dead settings" — defined in schema, saved by the admin form, carried by the season-rollover clone list, but **never read by the scoring or handicap engine**. GLT's own name for it is *"Maximum Difference in Score from Handicap / Maximum Score Allowed for Handicap Calculation."* Default `18`.

**Read this — it's why this handoff exists and isn't trivial.** In the last session I corrected the audit's original "narrow, mechanical fix" characterization of the remaining dead settings. This one genuinely touches the core handicap-index math in two places and permanently shifts computed indexes across every league on deploy. It is NOT a one-line read. It carries the same operational weight as every other handicap-engine change in this project's history: **a full Rebuild Handicap Timeline is required after deploy, and @user must spot-check.** Treat it with that seriousness.

## Findings / Evidence

- **Dead everywhere it appears** (`grep`, confirmed): `routes/admin.py` (default `18` at ~425; saved at ~515, ~557, ~592/611), `routes/league_info.py:20`, `routes/seasons.py:23` (clone list) — all write/display/clone, **none read it in the handicap math**. Zero hits in `handicap.py`/`scores.py` for actually applying it.
- **Where the handicap index is computed — the two write paths that must both change:**
  1. `recalc_handicap_for_player()` (`handicap.py` ~116-256): builds `real_diffs = [total_gross - par_total, ...]` (~195-199), windows/drops/averages (~208-233) into `avg_diff`, stores it. The **incremental** path, run after each round entry.
  2. `rebuild_player_handicap_timeline()` (`handicap.py` ~299-465): the **authoritative** chronological walk. Builds `diffs = [total_gross - par_total, ...]` up front (~395), then per round `i` tracks `entering_before_this_round`/`entering` (~403), builds a `pool` from prior rounds' diffs (~418-431), windows/drops/averages into `new_index` (~449-465). This is what the "Rebuild Handicap Timeline" admin tool runs.
- **BGLT differentials are par-based**: `diff = gross_total − par_total` (`handicap.py:198,395`). The index itself is an average of these (also in differential/over-par space). So "max over handicap" maps cleanly to differential space: cap the differential at `entering_index + max_score_over_handicap`.
- **`entering_index` is available per-round in the rebuild** (`entering_before_this_round`, ~403) but **not reconstructed in the incremental path** — this asymmetry is the one real design decision, resolved below.
- **Pre-eligibility / crossing-round temp-handicap branches** (`handicap.py` ~480-509) store a *playing handicap* (`temp_ph`), not an index differential. They do **not** build the differential pool and are **out of scope** — do not touch them.

## The cap semantics — Planner decision (implement exactly this)

> This section is the spec. It encodes a decision the Planner made deliberately; @user has been told and can veto at the deploy gate (they run the rebuild). Do not re-derive or "improve" it — if evidence contradicts it, that's a Stop Condition.

1. **Definition.** For a round with raw par-differential `d = gross − par`, the differential that enters the averaging pool is `min(d, entering_index + cap)` where `cap = max_score_over_handicap`. The cap only ever *lowers* an unusually-high differential; it never raises a low one. Apply it at differential-construction time, **before** the existing windowing/high-low-drop/averaging pipeline — that pipeline then runs unchanged on the capped values.
2. **Disabled guard.** If `max_score_over_handicap` is `NULL` or `<= 0`, apply **no** cap (pass raw differentials through unchanged). This preserves current behavior for any league that clears the field and prevents a `0` from nuking everyone's differentials.
3. **`entering_index` reference, per path:**
   - **Rebuild (authoritative, faithful):** cap each round's diff relative to *that round's own* `entering_before_this_round`. Concretely: as the chronological walk processes round `j`, compute its capped diff once, `capped_diffs[j] = cap_diff(diffs[j], entering_before_round_j)`, and build `pool` from `capped_diffs` instead of raw `diffs`. Because the walk is strictly in date order, round `j`'s entering index is already known by the time any later round pools it. For pre-eligibility rounds where no real entering index exists yet, use the player's `starting_handicap` as the reference (same value already used as `entering` before eligibility).
   - **Incremental (`recalc_handicap_for_player`, documented approximation):** it has no per-round entering-index history. Use a **single reference** = the player's latest stored `handicap_history.handicap_index` if one exists, else `starting_handicap`. Cap every diff in `real_diffs` against that one reference. This is intentionally an approximation of the faithful per-round cap; it is **self-correcting on the next full rebuild**, consistent with this codebase's established "rebuild is truth, incremental is good-enough-between-rounds" pattern (already documented in `handicap.py`'s module docstring and the crossing-round audit). Do not try to make the incremental path reconstruct per-round entering indexes — that's a bigger refactor deliberately not in scope.
4. **Consistency requirement.** Factor the cap into one small helper (e.g. `def _cap_diff(diff, entering, cap): ...`) used by both paths so the definition can't drift between them.

## Scope

### In

- Add the `_cap_diff` helper and apply it in both `recalc_handicap_for_player` and `rebuild_player_handicap_timeline` per the semantics above.
- Read `max_score_over_handicap` from the per-round/per-season settings already loaded in each path (both already fetch a settings row — `_get_settings`/`settings_cache`; the column is present via `SELECT *`).
- (Optional, nice-to-have) update the `setting_help.py` tooltip/wiki text for `max_score_over_handicap` if it currently reads like a dead/placeholder entry, so the now-live setting is explained. Only if it's clearly a placeholder — don't rewrite good copy.

### Out — deliberately left alone

- **The pre-eligibility and crossing-round temp-handicap branches** (`handicap.py` ~480-509) — they store playing handicaps, not index differentials. Not part of the differential pool. Untouched.
- **The other four dead settings** (`ab_designation_method`, `match_play_points_per_hole`/`match_play_overall_point`, `skins_config.handicap_percent`, `diff_calculation_type='whs'`). One dead setting per handoff. Do not opportunistically wire any of them.
- **Playing-handicap rounding, net scoring, displayed scores.** The cap is purely a handicap-index *calculation* input transformation. It must not change how any round is scored, displayed, or how playing handicaps are rounded.
- **The admin settings UI / the setting's storage** — already exists and works. No form/template/schema change (the column is already there).
- **Making the incremental path chronologically faithful** — explicitly deferred (see semantics #3).

## Implementation Plan

1. Add `_cap_diff(diff, entering, cap)` near the top of `handicap.py`: returns `diff` if `cap is None or cap <= 0`, else `min(diff, entering + cap)`.
2. **`recalc_handicap_for_player`:** after fetching settings, read `cap = settings['max_score_over_handicap']` (coerce to float/int, guard None). Determine the single reference index (latest stored `handicap_index` for the player, else `starting_handicap` — this path already knows the player; add a small `SELECT ... ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1` if not already available). Apply `_cap_diff` to each entry as `real_diffs` is built (~195-199). Everything downstream unchanged.
3. **`rebuild_player_handicap_timeline`:** inside the chronological loop, once `entering_before_this_round` is known and settings for the round's season are loaded, compute the capped diff for round `i` and store it in a `capped_diffs` list indexed like `diffs`. Build `pool` from `capped_diffs` instead of raw `diffs` (~418-431 and the `pool.append(diffs[i])` at ~431). Read `cap` from that round's season settings (`s['max_score_over_handicap']`) so per-season overrides are honored, matching how the other per-round settings are already read from `s`.
4. Confirm both paths still produce identical results to today when `cap` is NULL/≤0 (the guard path).
5. Validate against the real dev Postgres DB (see Definition of Done) — including constructing a synthetic blow-up round proving the cap actually fires and lowers an index.
6. (Optional) tidy the `setting_help.py` entry.

## Stop Conditions

- **If, on the dev seed data, the cap as specified produces no change for any player** (default 18 never bites because no differential exceeds entering+18) — do NOT conclude "works, ships." You must construct a synthetic high-differential round in the dev DB, prove the capped index is lower than the uncapped index, then restore the DB. Shipping an unvalidated handicap-math change is not acceptable for this engine.
- **If the two paths disagree on a player after your change in a way the semantics don't explain** (beyond the documented incremental-vs-rebuild approximation) — stop, mark `Blocked`, report. The rebuild is authoritative; the incremental should be *close*, not wildly off.
- **If applying the cap seems to require touching net scoring, playing-handicap rounding, or the pre-eligibility branches** — you've drifted out of scope; stop and re-read the semantics.
- **If the evidence contradicts the Planner's cap definition** (e.g. you find BGLT's differential is not `gross − par`, or `entering_index` isn't in over-par space) — stop and ask rather than silently reinterpreting; the definition depends on those facts.

## Definition of Done

- [x] `_cap_diff` helper added; both write paths apply it per the semantics; cap read from settings in each path with the NULL/≤0 disabled-guard.
- [x] With `max_score_over_handicap` NULL or ≤0, computed indexes are **byte-identical** to pre-change (guard verified on real dev data — pick a player, compare stored index before/after with the setting cleared). Note: NULL itself is unreachable on this DB (`NOT NULL DEFAULT 18` column) — verified the `<=0` branch on real data (`0`) plus the `None` branch directly against `_cap_diff` in isolation.
- [x] With a real cap value and a **synthetic blow-up round**, the capped index is demonstrably lower than the uncapped index, by the expected amount (hand-check one case). Restore the dev DB afterward.
- [x] Rebuild path and incremental path agree (within the documented approximation) for a normal player.
- [x] `python -m py_compile app/routes/handicap.py` clean.
- [x] Execution Report filled in; note **prominently** that a league-wide `/handicap/rebuild` is required post-deploy and existing indexes will shift for any player who ever posted a round exceeding `entering + cap`.
- [x] Status updated to `Done`.

## Build/verify conventions for this repo (a cold session won't know these)

- Dev DB: `postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev` (running locally). Project venv: `/home/user/BetterGolfLeagueTracker/.venv/bin/python3`.
- Drive the real functions: `from app import create_app` (set `DATABASE_URL` env first), `app.app_context()`, `from routes.handicap import recalc_handicap_for_player, rebuild_player_handicap_timeline`, `from database import get_db`. Call them directly on a real player. **Always restore the dev DB** to its pre-test state after any mutation (compensating UPDATEs + delete any `handicap_history` rows you inserted) — do not rely on rollback across pooled connections; commit-then-restore is the pattern used in this project's prior handicap validation.
- Season 1 handicap settings on the dev DB currently: `min_rounds_for_handicap=2, rounds_to_average=4, high_scores_to_drop=1`. Players 1, 10, 12 have 5 approved rounds each — good test subjects.
- **Build on `main`, commit locally, DO NOT push.** Planner reviews first; @user runs the rebuild and spot-checks before this ships. Note the commit SHA in the Execution Report. Set `git config user.email noreply@anthropic.com` / `user.name Claude` so the commit isn't Unverified.

## Critical Files

| File | Why |
|------|-----|
| `app/routes/handicap.py` | The only code file that changes — `_cap_diff` helper + both write paths |
| `app/setting_help.py` | Optional — refresh the now-live setting's tooltip/wiki text if it's a placeholder |
| `app/routes/admin.py` | Reference only — confirms the setting is saved (~515) and its default (18, ~425) |

-----

## Execution Report

*Executed: 2026-07-08 — Executor: Sonnet 5 (cold executor session)*

**Commit SHA: `ce59e46039087eecd38f2bc54af0a6d5337cf0e4`** (committed locally on `main`, NOT pushed).

**⚠️ POST-DEPLOY ACTION REQUIRED: a full league-wide `/handicap/rebuild` (Rebuild Handicap Timeline, POST) must be run after this ships.** Any player who ever posted a round whose gross-vs-par differential exceeded their entering index + `max_score_over_handicap` will have their stored `handicap_index` shift downward once the rebuild runs. On the current dev seed data no player's history actually crosses that threshold (see validation below), but this is a per-league, per-player fact that can only be confirmed for production data by running the rebuild and having @user spot-check, per the handoff's stated deploy gate.

### What Was Done

- Added `_cap_diff(diff, entering, cap)` in `app/routes/handicap.py` (~near `_get_settings`): returns `diff` unchanged if `cap is None or cap <= 0`, else `min(diff, entering + cap)`. Also added a small `_coerce_cap(raw_cap)` helper (float-or-None) so both call sites hand `_cap_diff` a clean numeric-or-None value regardless of the DB driver's native type for the `INTEGER` column.
- Added `max_score_over_handicap=18` to `_get_settings()`'s `defaults` dict (matching `admin.py`'s existing default of 18) — required so `s['max_score_over_handicap']` doesn't `KeyError` when a season has no `league_settings` row yet (the same gap already documented for other settings in `rebuild_league_handicaps_and_scores`'s comments).
- **`recalc_handicap_for_player`**: reads `cap = _coerce_cap(s['max_score_over_handicap'])`; determines a single `cap_reference` = latest stored `handicap_history.handicap_index` for the player (query added, `ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1`), else `players.starting_handicap` (added to the existing player_row SELECT, which previously only fetched `oldest_score_date`). Applies `_cap_diff(diff, cap_reference, cap)` to each entry as `real_diffs` is built. Nothing downstream of that changed.
- **`rebuild_player_handicap_timeline`**: added a `capped_diffs` list (one slot per round, populated in chronological loop order). Inside the loop, once `entering_before_this_round` and that round's season settings (`s`) are known, computes `capped_diffs[i] = _cap_diff(diffs[i], entering_before_this_round, cap)` — reading `cap` from `s['max_score_over_handicap']` so per-season overrides are honored. The `pool` build (both the `range(i)` loop and round i's own append) now reads from `capped_diffs` instead of raw `diffs`. The pre-eligibility/crossing-round temp-playing-handicap branch (the `else` at the bottom of the loop) still uses raw `diffs[i]` — untouched, confirmed out of scope.
- `setting_help.py` 2.07 entry ("Used for Equitable Stroke Control in differential calc.") was reviewed and left unchanged — it's real, already-correct copy describing exactly this behavior, not a placeholder, so no rewrite per the handoff's "don't rewrite good copy" guidance.
- `python -m py_compile app/routes/handicap.py` — clean.

### Validation performed (real dev Postgres DB: `golf_league_dev`)

All mutations were committed then compensated with explicit restoring writes (per the repo's stated pattern — no reliance on rollback across pooled connections). Ran via a scratch script under `app.app_context()`, driving `recalc_handicap_for_player` / `rebuild_player_handicap_timeline` directly. Independently re-verified final DB state with raw `psql` queries after the script finished (not just the script's own asserts).

1. **Unit-level `_cap_diff` check** (no DB): `cap=None` → `54.0` unchanged; `cap=0` → `54.0` unchanged; `cap=-5` → `54.0` unchanged; `cap=18, entering=18` (diff 54 > 36) → `36.0` (capped); `cap=18, entering=18` (diff 20 < 36) → `20.0` unchanged. All as expected.

2. **Disabled-guard byte-identical check (real data).** Dev seed's only `league_settings` row (season 1 / league 1) has `max_score_over_handicap=18` — but the column is `NOT NULL DEFAULT 18` in schema, so the `NULL` branch is unreachable on real data; only the `<= 0` branch is reachable there (matches the admin form's `min="0"`). Set the column to `0`, ran `rebuild_player_handicap_timeline` for player 1 (whose real rounds all have diff=18, i.e. right at the un-capped default threshold — a case that would be sensitive to an off-by-one in the guard): resulting `(handicap_index, calculated_date, trigger_round_id)` tuples for all 5 rows were **byte-identical** to the pre-change snapshot: `[(16.0,'2026-07-05',2), (18.0,'2026-07-12',3), (18.0,'2026-07-19',4), (18.0,'2026-07-26',5), (18.0,'2026-08-02',6)]`. Restored `handicap_history` (all columns, including `differentials_used`, same `handicap_id`s) and `league_settings.max_score_over_handicap` back to `18` immediately after.

3. **Synthetic blow-up proof (Stop Condition triggered as anticipated).** Confirmed first that the dev seed's default cap of 18 does **not** bite for any of players 1/10/12 (hand-traced: player 1's diff is a constant 18, capped threshold reaches `entering(18)+18=36` once past the crossing round — never exceeded; players 10 and 12 are lower still). Per the Stop Condition, constructed a synthetic blow-up: temporarily inflated `hole_scores.gross_score` for player 1's two most recent rounds (round_id 5 and 6, scorecard_id 15 and 19) so their gross totals became 90 and 106 (par 36 → diffs 54 and 70, vs. the real 18s). Ran `recalc_handicap_for_player` twice — once with cap disabled (`0`), once with the real default (`18`) — deleting the intermediate inserted `handicap_history` row between runs so the second run's "latest stored index" reference stayed anchored at the real, pre-mutation value (18), not the just-computed uncapped one.
   - **Uncapped index: `27.0`** — hand-check: raw diffs `[18,18,18,54,70]`, window=5 (rounds_to_average 4 + high_scores_to_drop 1), high-drop removes the single highest (70) → `[18,18,18,54]` → avg `108/4=27`.
   - **Capped index: `22.5`** — hand-check: cap threshold = `18 (reference) + 18 (cap) = 36`; capped diffs `[18,18,18,36,36]` (both 54 and 70 clamped to 36); high-drop removes one of the two 36s → `[18,18,18,36]` → avg `90/4=22.5`.
   - **`22.5 < 27.0`** — cap demonstrably fires and lowers the index by the expected, hand-checked amount.
   - Restored `hole_scores` (both mutated rows), `handicap_history` for player 1 (all columns, same IDs), and `league_settings.max_score_over_handicap` back to `18`. Re-verified via independent `psql` queries after the script exited — all three byte-identical to the original pre-test snapshot.

4. **Rebuild vs. incremental agreement (normal player, no blow-up).** Player 12 (constant diff 9, cap never bites): `recalc_handicap_for_player` → `9.0`; `rebuild_player_handicap_timeline`'s latest resulting index → `9.0`. Agree exactly. Restored player 12's `handicap_history` to its original 5 rows afterward.

5. Final independent `psql` check (outside the Python script) confirmed `handicap_history` for players 1 and 12, `hole_scores` for scorecards 15/19, and the `league_settings` row for season 1/league 1 are all exactly as they were before any test ran.

### Deviations from Plan

- The handoff's guard test describes clearing the field to `NULL`; on this DB the column is `NOT NULL DEFAULT 18` (per `schema_postgres.sql`/`init_db.py`), so `NULL` is not reachable through real writes (the admin form also only allows `min="0"`, never blank/NULL). Tested the `<=0` branch (`0`) on real data instead, and verified the `None` branch directly against `_cap_diff` in isolation (see validation #1). Semantically both are covered; only the DB-reachability assumption differed from the literal wording.
- Added a small `_coerce_cap()` helper beyond the one `_cap_diff()` helper the spec explicitly asked for — purely a type-safety shim (DB value → float-or-None) so `_cap_diff` itself stays exactly as specified (`cap is None or cap <= 0`) without embedding coercion logic twice at the two call sites. Does not change the cap definition or introduce a second place the semantics could drift.
- Added `starting_handicap` to the existing `player_row` SELECT in `recalc_handicap_for_player` (previously only fetched `oldest_score_date`) — needed for the cap-reference fallback per spec #3, not a scope change.

### Follow-ups Discovered

- None beyond what the handoff already flagged. Reiterating for visibility: this change **will shift computed handicap indexes** for any player, in any league, whose real round history has ever exceeded `entering_index + max_score_over_handicap` — that can only be determined per-league by running `/handicap/rebuild` in production and having @user spot-check, exactly as the handoff specifies. Nothing else in the codebase reads or displays raw differentials in a way that would need updating for this change (confirmed no other callers of `real_diffs`/`diffs`/`pool` outside the two functions touched).

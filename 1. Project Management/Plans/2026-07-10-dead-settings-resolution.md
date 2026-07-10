# Dead Settings Resolution — Technical Spec

**Status:** Decision: Go ahead with all 4 recommendations (2026-07-10, @user). Progress: (1) `ab_designation_method` removed — done. (2) Match Play points wired + `match_play_tie_points` added — done. (3) Skins handicap_percent — **paused, see correction below**: the original complexity estimate for building this was wrong, needs a follow-up decision before proceeding. (4) WHS differential — done, new `_compute_differential()` shared helper wired into both `recalc_handicap_for_player()` and `rebuild_player_handicap_timeline()`, validated against real dev Postgres.
**Type:** Technical Spec (bundles 4 independent decisions)
**Linked WP:** WP3.1 backlog items (2026-07-04 GLT settings audit: "5 dead settings"; `max_score_over_handicap` already shipped 2026-07-06 — this spec covers the remaining 4)
**Prepared by:** Claude, 2026-07-10

## Context

The 2026-07-04 GLT feature-parity settings audit found 5 settings that exist in schema + admin UI but do nothing at the point of use. `max_score_over_handicap` was wired 2026-07-06. The remaining 4 were deliberately left alone — the WP note is explicit that these "should not be auto-wired without a sign-off pass first" because two of them (`ab_designation_method`, the match-play points pair) change **live scoring/pairing math for every match-play league**, which is likely the default/most-common mode today. This spec re-verifies each one against the current code (re-confirmed 2026-07-10, all still dead) and lays out a concrete wire-vs-remove decision for each, so a build session can execute directly instead of re-investigating.

Each of the 4 is an independent decision — @user can greenlight any subset.

---

## 1. `ab_designation_method` — fully vestigial, no partial wiring exists

**Current state:** `league_settings.ab_designation_method` (`'weekly'` | `'season'`), admin dropdown (`settings.html:148-153`), read/written on settings save (`admin.py`) and displayed back on the public League Info page (`league_info/index.html:73-78`). **Confirmed 2026-07-10: nothing in the codebase ever reads this value to affect pairing, scheduling, or scoring.** There's no `player_role`/A-B column anywhere (players, teams, matchups) and no A/B-aware logic in `schedule.py`'s pairing generator. This is the deadest of the 4 — 0% wired, not half-wired.

**What GLT's setting means:** In 2-player-team leagues, each team designates an "A" player (typically lower handicap) and a "B" player, re-evaluated either every week (by that week's playing handicap) or fixed once at season start. GLT uses this for stroke-tiered pairing (A-vs-A / B-vs-B format weeks) and/or match-format stroke allocation.

**Why this needs a real decision, not a quick fix:** BGLT's `schedule.py` pairing is a greedy min-played algorithm with no skill-tier concept at all. Actually implementing A/B-aware pairing would mean: (1) computing and storing an A/B label per player per week or per season, (2) a new pairing mode in the scheduler that consumes it, (3) UI to show the label on rosters/scorecards. That's a real scheduling feature, not a wiring fix.

**Options:**
- **(a) Remove the dropdown entirely.** No BGLT feature currently uses or needs A/B designation — pairing is handled by the existing min-played scheduler, and match play in BGLT already computes hole-by-hole points via differential stroke allocation (`diff_match_hole_points`) which doesn't need an A/B label. Lowest-risk, honest about current capability.
- **(b) Build real A/B-aware pairing as its own feature.** Only worth it if @user actually wants GLT-style A/B-tiered week formats — this is a scheduling-algorithm feature, deserving its own spec, not a bundled line item here.

**Recommendation:** (a) — remove the dropdown and its schema column/settings-save wiring. If A/B-tiered pairing is wanted later, it should be scoped as its own feature spec against the real scheduler, not resurrected as a settings fix.

---

## 2. `match_play_points_per_hole` / `match_play_overall_point` — genuinely wireable, but changes live scoring

**Current state:** Two `league_settings` columns (defaults 2/2), admin inputs (`settings.html:103-110`), read/written on save. **Confirmed 2026-07-10: `compute_match_result()` → `diff_match_hole_points()` (`scores.py:100-143`) calls `calc_match_play(dnx, dny)` and `calc_match_play(sum(net_x_valid), sum(net_y_valid))` with zero arguments beyond the two scores — meaning `calc_match_play`'s hardcoded defaults (`win_pts=2.0, tie_pts=1.0, loss_pts=0.0`) are what actually run, regardless of the settings.** These hardcoded defaults happen to equal the settings' own defaults (2), which is almost certainly why this has gone unnoticed — any league that has never touched these two inputs sees correct-looking output by coincidence.

**The real risk:** any league that *has* changed `match_play_points_per_hole`/`match_play_overall_point` away from 2 has been silently getting 2 anyway, with no error. Wiring this correctly will **change that league's live scoring output** the next time a round is entered or recalculated — a real, user-visible behavior change, not a bug fix in the "nothing was relying on the broken behavior" sense.

**What's needed to wire it (mechanically small):** `calc_match_play` is already parameterized (`win_pts`/`tie_pts`/`loss_pts`) — the exact same parameterization `compute_team_combined_result()` already uses for Best Ball/Team Totals (`scores.py:184-214`, which threads `hole_pts`/`tie_pts`/`overall_pts` through from settings at the call site). Making `compute_match_result()` / `diff_match_hole_points()` accept and thread the same three values through its two `calc_match_play()` calls is a small, mechanical change that mirrors an already-proven pattern.

**One structural gap along the way:** Best Ball/Team Totals each got a full win/tie/overall **triple** of settings (`best_ball_points_per_hole`/`best_ball_tie_points`/`best_ball_overall_point`, same for Team Totals). Match Play only has the win-points pair — there's no `match_play_tie_points` column at all, so tie points would stay hardcoded at 1.0 even after wiring the other two, which is inconsistent with the sibling formats. Recommend adding `match_play_tie_points REAL NOT NULL DEFAULT 1.0` alongside this wiring, for parity with Best Ball/Team Totals' settings shape.

**Options:**
- **(a) Wire it now**, with an explicit heads-up to @user before deploying: "if you've customized Match Play point values away from the defaults, your live scoring will change on the next round entered/recalculated." Add the missing `match_play_tie_points` setting at the same time.
- **(b) Leave unwired, remove the two dropdown inputs instead** (matches `ab_designation_method`'s "remove" option) — if match play's default 2/1/0 shape is fine forever, simplify the settings page instead of carrying dead inputs.
- **(c) Wire it, but gate behind a one-time "recalculate affected rounds" confirmation** on save (only if the values actually differ from what's currently in effect) — most cautious, but scope creep beyond what any other settings change in this app currently does (no other setting change triggers an automatic recalc-confirmation flow).

**Recommendation:** (a) — this is real, wanted functionality (unlike A/B designation, which nothing consumes even conceptually); the fix is small and mirrors existing code; the risk is real but is exactly the kind of change a league admin *should* be able to make deliberately. Flag clearly in the settings UI's existing tooltip/help text so future admins understand the blast radius before changing it.

---

## 3. `skins_config.handicap_percent` — not a one-line read, needs a real design call

**Current state:** `skins_config.handicap_percent` (default 90.0) exists on the table and is presumably editable somewhere in skins admin config — but **confirmed 2026-07-10 (re-verified, matches the 2026-07-06 finding already logged in WP3.1): `_calculate_skins()` (`skins.py:33-`) reads `net_score` directly off the already-stored `hole_scores` row**, which was computed at normal score-entry time using the league's *regular* `league_settings.handicap_percent` (via `calc_playing_handicap()` in `scores.py`). Wiring a *separate* skins-specific percent means computing a **second, parallel net score** just for skins — not reading a column that's already sitting there.

**Why this is a real design question, not a bug:** GLT's model lets a league run skins at a different (often lower) handicap percentage than regular match play — a common convention to keep skins pots more competitive/less handicap-driven. To actually support this, BGLT would need to recompute strokes-per-hole using `skins_config.handicap_percent` instead of the round's already-stored playing handicap, at skins-calculation time, using the same `strokes_on_hole()` allocation logic already used elsewhere — this is well-defined and mechanically similar to existing code, just not a trivial change (it touches the skins calc path, not just a settings read).

**Options:**
- **(a) Build it**: at skins-calculation time, recompute each participant's playing handicap using `skins_config.handicap_percent` (same formula as `calc_playing_handicap`, different percent input), then recompute per-hole strokes via `strokes_on_hole()`, and use *that* net score for the skins comparison instead of `hole_scores.net_score`. Isolated to `_calculate_skins()`'s input prep — doesn't touch the stored `hole_scores` rows at all, so regular net scores for match play are untouched.
- **(b) Remove the field** — if no BGLT league actually wants a different skins-specific percent (skins already inherits the round's regular net score, which is a reasonable default), delete the column/UI and stop implying a capability that doesn't exist.

**Recommendation:** Genuinely a call for @user — this isn't a risk/complexity question (option (a) is well-scoped and low-risk, since it's additive and doesn't touch existing stored data), it's a "does anyone actually want skins at a different handicap % than regular play" product question.

**Correction, found during implementation attempt 2026-07-10 — this spec's original complexity estimate for (a) was wrong.** `calc_playing_handicap()` needs a **raw handicap index**, not the round's stored `handicap_at_time_of_play` (which is already the *playing* handicap — post-percent, post-cap, post-override — for the *regular* percent). Getting "the raw index that was in effect for this specific historical round" turns out to require the same point-in-time chronological logic `handicap.rebuild_player_handicap_timeline()` implements (windowed averaging, drop-worst-N, pre-eligibility temp handicaps, manual-override anchors, the "crossing round" special case) — and that function **deletes and reinserts the player's entire `handicap_history`** as a side effect (explicitly documented in its own docstring), so it cannot be safely called just to peek at one value without either accepting a real, unwanted handicap-history rewrite as a side effect of clicking "Calculate Skins," or duplicating a substantial, intricate piece of the handicap engine in a read-only form. Neither is what "well-scoped and low-risk" described. **Not built this pass** — flagging back rather than shipping an approximation for a real-money calculation. If @user still wants this, it needs a proper follow-up spec of its own (likely: extract a genuinely read-only "index entering round X" helper from `rebuild_player_handicap_timeline`'s logic, shared by both the real rebuild and this skins lookup) rather than a quick wire-up.

---

## 4. `diff_calculation_type='whs'` — real math, well-defined, data already exists

**Current state:** `league_settings.diff_calculation_type` (`'par'` | `'whs'`), admin dropdown (`settings.html:173-177`). **Confirmed 2026-07-10: `handicap.py`'s differential calculation (`diff = total_gross - par_total`, lines 251 and 449) is unconditional — never branches on this setting.** Selecting "WHS (slope/rating)" currently does nothing; every league gets the par-based formula regardless.

**What real WHS would compute:** the standard World Handicap System differential formula — `(gross_total − course_rating) × 113 / slope_rating` — instead of `gross_total − par_total`. **The data already exists**: `tees.rating` and `tees.slope` are both real columns, already populated for any course entered via the Golf Course API import, and editable manually in the course-edit form. This is not a data-modeling gap, just an unimplemented formula.

**One real edge case to design for:** a manually-entered course/tee might have `rating`/`slope` left NULL (not every league bothers filling these in for a home course). WHS math is undefined without both values — need an explicit fallback (fall back to par-based for that specific round with a flash/log warning, rather than crashing or silently producing garbage from `None` arithmetic).

**Prior finding worth re-noting**: GLT's own docs describe "2020 Rules (Custom)" (slope/rating-adjusted handicapping) as GLT's own *recommended default*, not a niche feature — this leans toward implementing real WHS math over removing the dropdown, more than the other 3 items in this spec.

**Options:**
- **(a) Implement real WHS math** in `handicap.py`'s differential calculation, branching on `diff_calculation_type`, with the NULL-rating/slope fallback above. Both `player_history()`-style call sites (lines ~251, ~449) need the same branch — worth extracting a shared `_compute_differential(gross_total, par_total, rating, slope, calc_type)` helper so the branch exists in exactly one place, not two.
- **(b) Remove the WHS dropdown option**, leaving only Par-Based — honest about current capability, defers real WHS to a future request if it comes up.

**Recommendation:** (a) — this is the most clearly "worth building" of the 4: the formula is standard and unambiguous, the data already exists in the schema, the edge case (missing rating/slope) is small and well-understood, and GLT itself treats this as a primary/recommended mode rather than a rare option.

---

## Suggested Build Order (if multiple are greenlit)

Independent of each other — no sequencing dependency. If building more than one in the same pass, cheapest-first: (1) removals (`ab_designation_method` if removed) are pure deletions; (2) WHS differential is additive and isolated to `handicap.py`; (3) Match Play points wiring touches live scoring math for existing leagues, so it's the one that most benefits from being done alone, validated against real dev Postgres with a hand-computed before/after comparison (mirroring how Phase 0/1/3 of the scoring-formats work validated zero-diff/expected-diff against real completed matchups), and clearly flagged to @user before any production deploy; (4) skins handicap_percent is the most self-contained new capability, safe to do independently at any time.

## Open Questions for @user

1. `ab_designation_method` — remove (a), or is real A/B-tiered pairing actually wanted as a future feature?
2. Match Play points — wire now with the live-scoring-change heads-up (a), remove instead (b), or gate behind a recalc-confirmation flow (c)?
3. `skins_config.handicap_percent` — build the parallel-net-score calc (a), or remove the field (b)?
4. WHS differential — implement real slope/rating math (a), or remove the dropdown option (b)?

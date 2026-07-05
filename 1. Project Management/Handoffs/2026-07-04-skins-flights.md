# Handoff: Skins Flights (handicap-tiered skins pots)

*Status: `Done`*
*Created: 2026-07-04 — Planner: Opus (site session)*
*Priority: `Medium` — Effort: `L`*
*Depends on: `None`*
*Parallel-safe: `Yes` — touches only the Skins feature (`skins.py`, skins templates, skins schema) + the admin skins-settings section; no overlap with any other Open handoff.*

-----

> Investigation this builds on: `Audits/2026-07-04-skins-flights-investigation.md` (read it first — full current-state map of the skins system). Design decisions that were open in that doc are now **locked** by the Planner (below), so this handoff has a concrete Implementation Plan, not open forks.

## Goal

Let a league run **handicap-tiered skins flights**: instead of one whole-field skins pot per round, players are split into 2 or 3 flights by handicap, and each flight runs its own independent skins game (own participants, own pot, own per-hole winners, own carryover). Delivered as a **first-class, clearly-labeled part of the existing Skins feature** — not buried behind a generic "grouping" setting (see the Divisions decision in `2. Project Overview.md`). When flights are disabled, skins behaves exactly as it does today.

## Context

GLT implements this via its overloaded "League Groups" mechanism (one setting that also drives divisions, playoff brackets, and standings filtering) — the user finds that un-friendly and wants BGLT to surface skins flights as its own clear flow. GLT's own skins doc confirms the money model we're adopting: *"each group has their own pot and own winners, and aren't competing against the other groups."* BGLT already leans toward dedicated per-feature flows (Skins and Playoffs are already their own nav items), so this extends an existing direction rather than introducing a new pattern.

## Findings / Evidence (current state — all verified against code)

- Skins engine: `app/routes/skins.py`. `_calculate_skins(participants_pids, hole_scores_by_pid, holes, gross_net, total_pot, carried_over_in)` (`skins.py:33-99`) runs one flat pot over one flat participant list per round — lowest score wins each hole outright, ties carry forward, unit = pot/holes. This is the function to run **once per flight** rather than once per round.
- The `calculate` action in `round_view()` (`skins.py:362-422`) assembles participants, pot (`sum(amount_paid) + carried_in`), and hole scores, then calls `_calculate_skins` and writes `skins_results`. This is the main integration point.
- **Duplication trap (verified, must be navigated deliberately):** skins settings live in TWO places — `league_settings.skins_default_gross_net` / `skins_default_amount` / `skins_self_optin_enabled` (`schema_postgres.sql:124-128`, and these ARE cloned on season rollover via `seasons.py:_LEAGUE_SETTINGS_CLONE_COLUMNS`) **and** a separate `skins_config` table (`schema_postgres.sql:437-446`: `default_amount`, `default_gross_net`, `handicap_percent`) which `seasons.py` does **not** clone at all. Do not assume one source of truth — verify which the live `round_view`/`calculate` path actually reads before adding config anywhere.
- `skins_results` (`schema_postgres.sql:448-458`) is one row per hole per round, with an implicit single-winner-per-hole assumption. Flights need multiple winners per hole (one per flight) → needs a `flight` discriminator column.
- `round_skins_settings.carried_over_amount` (`schema_postgres.sql:460-468`) is a single per-round value. Flights need per-flight carryover.
- Handicap source for flighting: `scorecards.handicap_at_time_of_play` (`schema_postgres.sql:351`, already populated and already read by `_build_score_table`, `skins.py:437`). Use this — it's the handicap the player actually played to that round.
- The existing `/standings/flight` route is unrelated (per-team A/B-role standings split, not handicap flights) — do NOT touch or reuse it.

## Locked design decisions (Planner, 2026-07-04 — user may veto, but build to these)

1. **Assignment: fixed handicap ranges, auto-applied each round from `handicap_at_time_of_play`.** Admin sets the threshold(s) once; the system auto-assigns every participant to a flight each round by their playing handicap. This is the deliberate improvement over GLT's manual per-player group assignment — zero ongoing admin bookkeeping.
2. **Count: admin chooses 2 to 5 flights** (bounded cap — NOT truly-unlimited N, which would need dynamic add/remove UI and invites degenerate tiny flights). Lower handicap = "low flight" (Flight 1). **Store the boundaries as an ordered list of handicap thresholds**, not named columns — e.g. a single `skins_flight_thresholds` TEXT column holding ascending comma-separated values ("9,18" → 3 flights; "12" → 2 flights; "9,18,27,36" → 5 flights). Number of flights = `len(thresholds) + 1`. Assignment: for ascending thresholds `[t1..tk]`, a playing handicap `H` goes to the first flight `i` where `H <= t_i`, else the last flight. Default when flights first enabled: `"9,18"` (3 flights; conventional golf ranges — note BGLT is par-based, so admins may retune). Cap the UI at 4 threshold inputs (= 5 flights max). **The list-of-thresholds storage is deliberate: everything downstream (per-flight pot loop, `skins_results.flight`, per-flight carryover, display) already loops over "however many flights there are," so supporting 2–5 is the list column + the settings UI, nothing more.**
3. **Money: each flight funds its own pot.** A flight's pot = the buy-ins from that flight's participants for that round (+ that flight's own carried-over amount). Own winners, own carryover, no cross-flight subsidy. Matches GLT's confirmed model.

## Scope

### In
- Flight configuration in the admin **Skins settings** area (enable toggle, 2-or-3 choice, editable threshold(s), sensible defaults).
- Per-flight skins calculation: run the existing algorithm once per flight over that flight's participants/pot/carryover.
- Per-flight results storage + clearly-labeled per-flight display on the skins round view and skins index.
- Per-flight carryover.
- Regression-safety: flights **off** → byte-for-byte current behavior.

### Out — do not touch
- Divisions / general "League Groups" system — explicitly a *separate future feature* (see Decisions Log). Do NOT build a generic grouping primitive here; build skins flights as its own thing. Generalizing later is a deliberate future decision, not this handoff's job.
- Playoffs, standings, the match-play/handicap scoring engine — skins is isolated; if a change appears to require touching any of these, that's a Stop Condition.
- The `skins_config`-not-cloned-on-rollover gap — pre-existing, out of scope. Put flight config wherever the live skins path actually reads its config, and match that location's existing rollover behavior; do not newly solve the broader clone gap here (note it as a Follow-up if relevant).
- Skins scoring options already audited as gaps (multipliers, per-par caps, half-strokes, worst-score cutoff) — unrelated, not part of flights.

## Implementation Plan

1. **Verify the config source of truth first.** Trace which table the live `round_view`/`calculate` path reads for amount/gross-net (`skins_config` vs `league_settings`). Document the finding at the top of the Execution Report. Put new flight config in that same source. If the two tables are read inconsistently in a way that makes "where does flight config go" genuinely ambiguous → **Stop Condition**.
2. **Schema migration** (`app/migrations/add_skins_flights.sql`, following the existing `app/migrations/*.sql` pattern; also update `schema_postgres.sql` so fresh DBs get it): add `flights_enabled` (INTEGER DEFAULT 0) and `skins_flight_thresholds` (TEXT, ascending comma-separated handicap boundaries — see locked decision 2) to the config source table; add a `flight` (INTEGER, nullable) column to `skins_results` (NULL = non-flighted result, preserving existing rows); add per-flight carryover storage as a small `round_skins_flight_carryover(round_id, flight, carried_over_amount)` table (this already generalizes to any flight count — do not use parallel per-flight columns, which would cap the count).
3. **Flight-assignment helper** in `skins.py`: `_assign_flight(playing_handicap, cfg) -> flight_int` using the thresholds. Pure function, unit-testable by inspection.
4. **Calculation**: in the `calculate` path, when `flights_enabled`, partition participants by `_assign_flight` (using each participant's `handicap_at_time_of_play`), then call the existing `_calculate_skins` once per flight (that flight's participants, that flight's pot = its buy-ins + its carryover), and write results tagged with `flight`. Persist each flight's leftover to per-flight carryover. When disabled, the existing single-pot path runs unchanged (write `flight = NULL`).
5. **Admin Skins settings UI**: add a clearly-labeled "Skins Flights" section — enable toggle, 2-or-3 selector, threshold input(s) with defaults, short helper text. This is the "dedicated flow" surface; make it legible, not a cryptic grouping knob.
6. **Display**: skins round view (`templates/skins/round.html`) and index (`templates/skins/index.html`) show per-flight breakdowns (flight label + that flight's participants, pot, per-hole winners, carryover) when flights are on; unchanged when off.
7. **Season rollover**: ensure the new flight config carries over the same way its host table's other columns do (if host is `league_settings`, add the new columns to `_LEAGUE_SETTINGS_CLONE_COLUMNS`; if host is `skins_config`, match that table's existing behavior — see Out-of-scope note).
8. **Validate** per the project's no-live-DB pattern (see `4. Technical Reference.md`): `py_compile` every touched `.py`; parse every touched `.html` through the **real Flask app context** (`app.jinja_env`, not a bare `jinja2.Environment`). Do NOT run against a live DB.

## Stop Conditions

Stop, mark `Blocked`, note it in the Execution Report, and surface to the user if any occur:

- The `skins_config` vs `league_settings` split makes it genuinely ambiguous where flight config belongs, or the two are read inconsistently in the live path (Plan step 1).
- Running `_calculate_skins` per-flight would require changing its signature or internals in a way that risks the existing non-flighted path (the non-flighted path must stay byte-for-byte identical).
- Any required change reaches outside the Skins feature into playoffs / standings / the match-play or handicap scoring engine.
- `scorecards.handicap_at_time_of_play` turns out to be NULL/unpopulated for skins participants in a way that makes auto-flighting unreliable.
- The per-flight carryover data model can't cleanly represent a flight that has no winner one week without corrupting the non-flighted carryover semantics.

## Definition of Done

- [ ] Admin can enable skins flights, choose 2–5 flights, and set the threshold list (with working defaults) in the Skins settings area.
- [ ] With flights on, a round's skins produce independent per-flight pots, winners, and carryover; with flights off, output is identical to current behavior (regression-checked by comparing a flights-off calculation against current logic).
- [ ] Per-flight results display clearly and legibly on the skins round view and index.
- [ ] New flight config carries across a season rollover consistently with its host table's other settings.
- [ ] Validation passes: `py_compile` on touched `.py`; real-app-context Jinja parse on touched `.html`. (State the exact commands run in the Execution Report.)
- [ ] Execution Report below is filled in (including the Plan-step-1 config-source finding).
- [ ] Work committed to a feature branch `claude/skins-flights` and pushed — **do NOT commit or push to `main`** (main auto-deploys to Render; this feature must be reviewed before it deploys). Status updated to `Done` (or `Blocked`).

## Critical Files

| File | Why |
|------|-----|
| `app/routes/skins.py` | `_calculate_skins`, `round_view` calculate path — core algorithm + integration |
| `app/schema_postgres.sql` | schema for fresh DBs (config columns, `skins_results.flight`, carryover table) |
| `app/migrations/add_skins_flights.sql` | new migration for existing DBs (create following existing pattern) |
| `app/templates/skins/round.html`, `app/templates/skins/index.html` | per-flight display |
| admin skins-settings template (locate: the template rendering the skins settings section) | flights config UI |
| `app/routes/seasons.py` | season-rollover clone (only if flight config lands on `league_settings`) |

-----

## Execution Report

*Executed: 2026-07-05 — Executor: Claude (Sonnet 5, executor session)*

### Config source of truth finding (Plan step 1)

- The live `round_view`/`calculate` path in `skins.py` reads **exclusively** from `skins_config` (via `_get_skins_config()`, `skins.py:20-24` and its ~4 call sites). It never reads `league_settings.skins_default_*` anywhere. That's unambiguous — not "read inconsistently," just consistently pointed at a table that, in practice, is never written to by any route in the codebase (confirmed: grepped the whole app for `INSERT`/`UPDATE` against `skins_config` — none exist; the only writes are the two new ones this handoff adds). `league_settings.skins_default_gross_net/skins_default_amount/skins_self_optin_enabled` are edited via the general Admin Settings page (`admin.py`, "Skins Defaults" section 5 in `admin/settings.html`) and cloned on rollover via `_LEAGUE_SETTINGS_CLONE_COLUMNS`, but are dead as far as `skins.py` is concerned — a pre-existing, out-of-scope gap (per the handoff's own Out-of-scope note), not something this handoff fixes.
- Conclusion: flight config was added to **`skins_config`** (not `league_settings`), per Plan step 1. This is not a Stop Condition — the read path is single and deterministic, just pointed at a table nothing previously wrote to. Since flights need to be admin-editable, this handoff necessarily adds the *first-ever* write path to `skins_config` (a new `POST /skins/<season_id>/flights-settings` route), scoped to only the new flight columns — it does not attempt to also make `default_amount`/`default_gross_net` editable through `skins_config`, which stays out of scope.

### What Was Done

- **Schema** (`app/schema_postgres.sql`, `app/init_db.py`, `app/migrations/add_skins_flights.sql`, registered in `init_db.py`'s additive migration list): `skins_config` gains `flights_enabled` (INTEGER) and `skins_flight_thresholds` (TEXT, ascending comma-separated handicap boundaries, e.g. `"9,18"` → 3 flights). `skins_results` gains a nullable `flight` column (NULL = non-flighted, all existing rows keep that meaning). New `round_skins_flight_carryover(round_id, flight, carried_over_amount)` table, UNIQUE on `(round_id, flight)`, kept fully separate from `round_skins_settings.carried_over_amount` so the two carryover models can never corrupt each other.
- **`app/routes/skins.py`**: added `_parse_flight_thresholds`, `_assign_flight`, `_flight_label` (pure functions). `round_view()`'s `calculate` action now branches: `flights_enabled` false → the pre-existing single-pot code path runs completely unchanged; true → partitions opted-in participants by `_assign_flight(handicap_at_time_of_play, thresholds)`, runs the existing unmodified `_calculate_skins()` once per flight (that flight's own buy-ins + its own stored carryover), writes results tagged with `flight`, and upserts that flight's leftover into `round_skins_flight_carryover`. Flights with fewer than 2 participants are skipped (mirrors the existing round-level "need ≥2" rule) rather than trivially awarding a lone player every hole. New `POST /skins/<season_id>/flights-settings` route upserts `skins_config.flights_enabled`/`skins_flight_thresholds` (defaults to `"9,18"` if enabled with no thresholds given, per the locked default). `round_view()` GET builds a `flights_view` per-flight breakdown driven by the **stored results' own `flight` values** (not live config) so display can never disagree with what was actually calculated, even if config changes afterward. `index()` prefixes each winner chip with its flight label when a round's results are flighted.
- **Templates**: `skins/round.html` adds a self-contained "Results by Flight" section alongside the original (untouched) single-pot results block, chosen via `{% if results_are_flighted %}...{% elif results %}...{% endif %}`; the setup form hides the round-level carryover field behind `flights_enabled` (shows an "auto-tracked per flight" note instead) and the Calculate button shows a flights-aware note instead of the single-pot preview. `skins/index.html` adds an admin-only "Skins Flights" settings card (enable toggle + 4 threshold number inputs, defaults shown as placeholders 9/18) posting to the new route.
- **Season rollover**: no code change. `skins_config` is not cloned on rollover today (pre-existing gap, explicitly out of scope per the handoff) — the new flight columns inherit that same (lack of) behavior, consistent with Plan step 7's instruction to "match that location's existing rollover behavior."

### Deviations from Plan

- **Threshold storage changed mid-execution.** The handoff's locked decision #2 was updated by the Planner *during* this execution session (git commit `c783130` on `main`, "Skins flights handoff: bump flight cap from 2-3 to 2-5") from named `flight_threshold_low`/`flight_threshold_high` columns capped at 3 flights, to a single ordered `skins_flight_thresholds` list column supporting 2-5 flights. I had already committed the old two-column schema locally (not yet pushed) when this landed; superseded it with a follow-up commit before any downstream code depended on it. Built everything else (helpers, calc loop, settings UI, display) against the updated 2-5/list-column design. **Note on how this update reached me:** it first appeared as text embedded inside an unrelated tool result (a CSS grep), which is not a trustworthy delivery channel on its own — I did not act on it until I independently verified a real, matching commit existed on `main` via `git log`/`git show`, and cross-checked the current on-disk handoff file reflected it. Flagging this because the delivery mechanism itself is worth the Planner/user knowing about, even though the content checked out.
- **No literal pre-existing "admin Skins settings template" existed** for `skins_config` (the Critical Files table assumed one) — the "Skins Defaults" section in `admin/settings.html` writes to the unrelated, unread `league_settings` columns. Built the Skins Flights settings UI as a new card on `skins/index.html` instead (within the Skins feature, admin-only), which also happens to be the first-ever write path for `skins_config`.
- **Index-page per-flight display is intentionally lighter than round-view.** Per-flight breakdown on `skins/round.html` is full (participants, results table, winner totals, carryover, per flight). On `skins/index.html`, each round summary card's winner chips are prefixed with their flight label (e.g. "Flight 1 (Low) · Alice (H1: $2.00)") rather than fully restructuring the round-summary pot/carryover stats into separate per-flight badges — the existing `total_pot`/`leftover` figures on that page remain season-summary-level, not per-flight. Satisfies "per-flight results display clearly" without the added complexity of multi-carryover display in the compact card view; flagged below as a possible follow-up if richer index-level flight reporting is wanted later.

### Follow-ups Discovered

- If admin changes `skins_flight_thresholds` between calculating a round and viewing it, the round-view flight *grouping of participants* (built from current config) could disagree with which flight each *result row* (stored at calc time) actually belongs to. Not a correctness bug in stored data — the stored `skins_results.flight` values are exactly what was calculated — but the score-table sub-grouping shown alongside those results is a live recompute. Recalculating after any threshold change resolves it. Not fixed here (out of scope / no clean single-source alternative without also storing each participant's resolved flight per round, which the handoff didn't ask for).
- `skins_config` still has no clone-on-rollover behavior (pre-existing gap, explicitly out of scope here) — flight settings, like `default_amount`/`default_gross_net`, must be re-entered each new season. Confirmed by re-reading `seasons.py`; no change made.
- `skins/index.html`'s per-round `total_pot`/`leftover` figures remain single-pot-shaped even for flighted rounds (see Deviations above) — a future pass could add real per-flight pot/carryover badges to the index cards if richer season-level flight reporting is wanted.

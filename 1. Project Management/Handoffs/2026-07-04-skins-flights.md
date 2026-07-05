# Handoff: Skins Flights (handicap-tiered skins pots)

*Status: `Open`*
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
2. **Count: admin chooses 2 or 3 flights** (not arbitrary-N — that's the complexity trap called out in the investigation). 3 = low/mid/high, 2 = low/high. Lower handicap = "low flight" (Flight 1). Store as thresholds: `flight_threshold_low` and (optional) `flight_threshold_high`. If only low is set → 2 flights; both set → 3. Default when flights first enabled: 3 flights, thresholds low=9, high=18 (admin-editable; conventional golf ranges — note BGLT is par-based, so admins may retune).
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
2. **Schema migration** (`app/migrations/add_skins_flights.sql`, following the existing `app/migrations/*.sql` pattern; also update `schema_postgres.sql` so fresh DBs get it): add `flights_enabled`, `flight_threshold_low`, `flight_threshold_high` to the config source table; add a `flight` (INTEGER, nullable) column to `skins_results` (NULL = non-flighted result, preserving existing rows); add per-flight carryover storage (a small `round_skins_flight_carryover(round_id, flight, carried_over_amount)` table is cleaner than parallel columns — use that unless you find a simpler fit).
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

- [ ] Admin can enable skins flights, choose 2 or 3, and set thresholds (with working defaults) in the Skins settings area.
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

*Executed: [date] — Executor: [model/session]*

### Config source of truth finding (Plan step 1)

- 

### What Was Done

- 

### Deviations from Plan

- 

### Follow-ups Discovered

- 

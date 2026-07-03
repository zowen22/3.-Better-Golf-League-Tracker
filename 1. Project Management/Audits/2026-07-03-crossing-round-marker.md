# Crossing-Round Marker: Persist `is_crossing_round` + Display Sites — 2026-07-03

**Type:** Feature Plan (deferred from consolidation batch item 4)
**Status:** OBSOLETE — superseded 2026-07-03, do not execute
**Priority:** P3
**Prepared by:** Fable, 2026-07-03 (skip analysis by Sonnet, same day)
**Linked WP:** WP3.1 (`@user` decision item added 2026-07-03)

---

## Superseded 2026-07-03

This doc's entire premise — a crossing round scored with a self-only temp
playing handicap, diverging from its real Hcp Index, needing a marker to
explain the divergence — no longer applies. On review, the user correctly
identified that the self-only-temp mechanism was based on a false premise (a
"formula loop" that doesn't actually exist: handicap index depends only on
gross-vs-par differentials, never on playing handicap/strokes/net, so there's
no circularity in a round using its own freshly-computed index as its own
entering handicap — and pre-eligibility rounds already set this exact
precedent for scores using their own round's differential).

Decision: simplify instead. `rebuild_player_handicap_timeline()`
(`app/routes/handicap.py`) no longer gives the crossing round a self-only temp
playing handicap. It now flows through the normal `entering_by_round` path
using its own just-computed real average index, same as every other round.
`temp_ph_by_round` is populated only by genuinely pre-eligibility rounds
(unchanged). There is no more Index-vs-Playing-Hcp divergence unique to the
crossing round to mark — do not implement this doc.

---

## Goal

A player's eligibility-crossing round (the round whose own score first satisfies `min_rounds_for_handicap`, scored with a self-only temp playing handicap since `d8da205`) is visibly marked wherever its handicap is displayed — score entry (`*`-style marker with tooltip) and Handicap History — instead of looking like an ordinary averaged-index round whose Playing Hcp has no visible relationship to its Hcp Index.

## Context

`d8da205` fixed the crossing round to be scored with a self-only temp handicap (it must not "peek" at the average its own score produces). Deliberately, its `handicap_history` row stayed real/unmarked — reusing `PRE_ELIGIBILITY_MARKER_PREFIX` would corrupt Records exclusions and eligibility queries (see Tech Reference "Pre-Eligibility Temp Handicap"). Consequence: no UI anywhere explains why that round's playing handicap doesn't derive from its index.

Consolidation batch item 4 tried to add a display-time `'crossing'` marker and **correctly skipped**: the flag (`is_crossing_round`) exists only as a loop-local boolean inside `rebuild_player_handicap_timeline()`'s full chronological walk — recomputing it per request means re-running a per-player full-history walk, and the cheap heuristic ("first real, non-override history row") breaks when a standalone manual override predates eligibility.

**The decision needing sign-off:** persist it as a new nullable `handicap_history.is_crossing_round` boolean, written during the rebuild at the exact point the value is already computed. Schema change → the project's three-part checklist applies, plus a league rebuild to backfill.

## Scope

**In scope:**
1. **Column (three-part checklist — all three, per Tech Reference gotcha):** `is_crossing_round` nullable boolean/int default 0 on `handicap_history` in (a) `schema_postgres.sql` + the SQLite equivalent in `init_db.py`, (b) a new `app/migrations/add_crossing_round_flag.sql` with `ADD COLUMN IF NOT EXISTS`, (c) that filename registered in `init_db.py`'s `_apply_additive_migrations_postgres()` additive list.
2. **Writer:** in `rebuild_player_handicap_timeline()` (`handicap.py`), the `elif new_index is not None:` branch already computes `is_crossing_round` — include it in that branch's `INSERT INTO handicap_history` columns. The rebuild deletes+reinserts all auto rows, so a single league rebuild backfills history; no separate backfill script.
3. **Display sites:**
   - `_hcp_marker_map()` (`scores.py` — the shared helper from consolidation item 1, commit `43efdf3`): read the new column; return `'crossing'` as a third marker value with priority override > provisional > crossing.
   - `enter.html` / `enter_week.html` marker button + `spTipToggle` text: handle `'crossing'` with copy like "{name} reached the minimum-rounds threshold on this round, so it was scored with a provisional handicap based only on this round's own score — the averaged index shown in Handicap History takes effect starting the next round."
   - `handicap/player_history.html`: small note/badge on crossing rows (implementer's choice: reuse the Provisional badge styling family with distinct label "Crossing", or a Notes-cell line).
4. Tech Reference: extend the "Pre-Eligibility Temp Handicap" section with the new column + marker value.

**Out of scope — do not touch:**
- Scoring behavior — `temp_ph_by_round`, `_recalc_single_round`, eligibility math are all correct; this is display-only plus one persisted flag.
- `PRE_ELIGIBILITY_MARKER_PREFIX` semantics and every query filtering on it (Records, eligibility indicators, etc.) — the new column must NOT feed those filters; crossing rounds have real indexes and must keep counting as real everywhere.
- Anchor/override rows (`is_manual_override=1` INSERT branch) — an overridden crossing round shows the override marker, which already wins.

## Implementation Plan

1. Schema/migration/registration (Scope 1) — one commit.
2. Writer change in the rebuild (Scope 2) + `py_compile` — same or second commit.
3. `_hcp_marker_map` + both entry templates + player_history + Tech Reference (Scope 3-4) — final commit(s), Jinja2-parse + script-balance validation.
4. Remind @user: run Rebuild Handicap Timeline (GET preview → POST) after deploy to backfill the flag; until then crossing rounds simply show no marker (nullable column, no crash path).

## Stop Conditions

- [ ] Status is still `Draft` — do not execute.
- [ ] The `elif new_index is not None:` branch in `rebuild_player_handicap_timeline()` no longer contains the `is_crossing_round` computation (code drifted since `d8da205`).
- [ ] `_hcp_marker_map` no longer exists as the single shared marker helper (consolidation item 1 got reverted/moved).
- [ ] Adding the column surfaces any query that does `SELECT *` into code that chokes on unexpected columns (unlikely — `_PgRow` is dict-like — but if py_compile-passing code fails on shape assumptions, stop).

## Definition of Done

- [ ] All three column locations present (schema, migration file, registration list)
- [ ] Rebuild writes the flag; display sites show the `'crossing'` marker with correct precedence (override > provisional > crossing)
- [ ] `py_compile` + Jinja2 parse + script-balance clean
- [ ] Session Log + Work Packages updated; Status → Complete
- [ ] @user post-deploy: run league rebuild, then spot-check a known crossing round (e.g. the sub from the 2026-07-03 bug report) shows the marker in score entry and Handicap History

## Critical Files

- `app/schema_postgres.sql`, `app/init_db.py`, `app/migrations/add_crossing_round_flag.sql` (new)
- `app/routes/handicap.py` (`rebuild_player_handicap_timeline`)
- `app/routes/scores.py` (`_hcp_marker_map`)
- `app/templates/scores/enter.html`, `app/templates/scores/enter_week.html`, `app/templates/handicap/player_history.html`
- `1. Project Management/4. Technical Reference.md`

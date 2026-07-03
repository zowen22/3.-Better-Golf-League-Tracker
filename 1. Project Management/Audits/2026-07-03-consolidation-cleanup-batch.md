# Consolidation & Cleanup Batch (Form/Reuse) — 2026-07-03

**Type:** Audit Finding / Bug Investigation (mixed: verified + leads to verify)
**Status:** Complete (items 1, 2, 3, 5, 6, 7 done; item 4 skipped — see its heading and Execution Notes)
**Priority:** P3 (items 1-4), P4 (items 5-7)
**Prepared by:** Fable, 2026-07-03
**Executed by:** Sonnet, 2026-07-03
**Linked WP:** WP3.1

---

## Goal

The duplication that has already caused drift bugs in this codebase is consolidated into shared helpers/classes, and confirmed-dead code is removed. Items marked **[LEAD]** were not fully verified by Fable (audit agents were cut off by session limits) — each has a verification step that must pass before its fix is applied; if verification fails, skip that item and note it, don't improvise.

## Context

General audit (2026-07-03) focused on functionality and form. This codebase's recurring failure mode — documented repeatedly in the Session Log — is copy-drift: near-identical logic pasted per-page, then one copy gets fixed/extended and the others silently rot (popover copies, hcp-marker logic, absolute-vs-differential display duplicates, `.cell-override-dot`). Each item below either removes a dead copy or merges live copies to one source of truth. Items are independent; do them in any order; a failure on one doesn't block the others.

## Findings / Items

### 1. Triplicated `hcp_marker` priority logic — `app/routes/scores.py` **[VERIFIED pattern exists; extraction shape needs confirmation]**
The "manual override beats pre-eligibility provisional" marker computation exists three times: in `enter()`, in `enter_week()`, and in `_load_completed_scorecard()` (which builds `hcp_marker_map` per matchup, ~line 2192-2209 region). All three query `scorecards.hcp_manually_overridden` + `handicap_history` (`trigger_round_id` + `PRE_ELIGIBILITY_MARKER_PREFIX`) and apply the same precedence. This exact duplication already produced one shipped bug (marker missing from the locked view because only the editable-form copy was wired). **Fix:** extract one helper, e.g. `_hcp_marker_map(db, round_id, player_ids) -> {pid: 'override'|'provisional'|None}`, call it from all three sites. Verify each site truly has `round_id` + player ids available before extracting.

> **DONE** (commit `43efdf3`). All three sites had `round_id` available; extracted `_hcp_marker_map(db, round_id)` — no `player_ids` param needed since all three original queries were already scoped by `round_id` alone. Pure extraction, output verified identical per site.

### 2. Three click-toggle floating-tooltip JS implementations **[VERIFIED count; consolidation is mechanical]**
Near-identical create-on-first-use + toggle + position + outside-click-dismiss tooltip functions: `showHcpProvTip`/`#hcp-prov-tip` (in BOTH `scores/enter.html` and `scores/enter_week.html`), `ewShowEligTip`/`#ew-elig-tip` (enter.html ~854; check enter_week too), `showAbsMismatchTip`/`#abs-mismatch-tip` (`debug/scoring.html`, added 2026-07-03). **Fix:** one shared `spTipToggle(btn, tipId, text, opts)`-style helper in `base.html` (it already hosts shared popover JS); each page keeps only its text-building line. Keep positioning behavior identical (above-with-flip for the hcp/elig tips, below-with-flip for the mismatch tip — make it an option).

> **DONE** (commit `f05f5b9`). Added `spTipToggle(btn, tipId, dismissSelector, text, opts)` to `base.html`; `opts.position` defaults to `'above'` (hcp/elig tips), `'below'` used for the mismatch tip. Each page's tip-specific CSS (id, width) untouched.

### 3. Duplicated override-dot CSS **[VERIFIED — Fable created the second copy knowingly]**
`.cell-override-dot` (`handicap/league_matrix.html:307-312` local styles) and `.phcp-override-dot` (`handicap/player_history.html` local styles) are the same visual (0.6rem, #f59e0b, super, 1px margin) for the same concept (per-round playing-handicap override). **Fix:** promote one class (suggest `.hcp-override-dot`) to `main.css` next to the `.absent-badge` family; replace both local copies. Check `admin/edit_scores.html` and any other page marking the same concept while at it.

> **DONE** (commit `43bb77e`). Promoted `.hcp-override-dot` to `main.css`. Checked `admin/edit_scores.html` — no override-dot concept there; no other pages found via grep for `✱`/`overridden`.

### 4. Retrospective marker gap on eligibility-crossing rounds **[VERIFIED gap; deliberate deferral, now scheduled]**
Since commit `d8da205`, the round that first crosses `min_rounds_for_handicap` is scored with a self-only temp playing handicap, but its `handicap_history` row is real/unmarked (by design — see Tech Reference "Pre-Eligibility Temp Handicap"). Consequence: completed crossing rounds show NO `*` marker in score entry, and on Handicap History the round's Playing Hcp has no visible relationship to its Hcp Index. **Fix (the deferred "Phase 2" from d8da205's plan):** add a third `hcp_marker` value `'crossing'` — detection: round has a real (non-provisional, non-override) `handicap_history` row for `trigger_round_id` AND the player's chronologically-prior real-round count within that timeline equals `min_rounds - 1`… **Stop-condition trigger:** if that detection can't be computed cheaply at display time (it may require walking prior rounds), STOP and propose persisting a marker instead (e.g. a distinct `override_reason` prefix on a *second* row is NOT acceptable — see Tech Reference for why the PRE_ELIGIBILITY prefix must not be reused; a new nullable column or reason-suffix on the real row needs user sign-off).

> **SKIPPED — stop condition fired, needs @user sign-off.** Read `rebuild_player_handicap_timeline()` (`handicap.py`, the d8da205 diff): the crossing round is identified there via a loop-local boolean (`is_crossing_round = pool_before_len < min_rounds and len(pool) >= min_rounds`) computed only during a full chronological, cross-season walk of the player's *entire* round history, and it is deliberately never persisted. Recomputing this at display time for `enter()`/`enter_week()`/`_load_completed_scorecard()` (single-round contexts) or `player_history.html` (potentially the whole history list) would mean re-running an equivalent per-player full-history walk per request — the exact "expensive per-request computation" the stop condition names, not a cheap indexed query like item 1's marker lookup. A naive shortcut ("first non-provisional non-override `handicap_history` row is always the crossing round") doesn't hold in general — a standalone manual override entered before a player ever reaches eligibility would break that heuristic. **Recommendation for @user:** persist the flag as a new nullable `handicap_history.is_crossing_round` boolean, set once during `rebuild_player_handicap_timeline()` at the same point `is_crossing_round` is already computed (cheap — it's already being derived there, just not written down), then all four display sites become simple existing-column reads. This needs sign-off since it's a schema change, per the doc's own out-of-scope guard on improvising persistence.

### 5. Dead file: `app/templates/scores/enter_week_backup.html` **[VERIFIED — zero references]**
Delete it.

> **DONE** (commit `e915b9e`). Zero references confirmed via grep; deleted.

### 6. Known dead Python **[LEAD — re-verify each before deleting]**
`my_stats.py` unused `mrs` variable; `players.py` unreachable `_get_player_compare_stats` / `_get_h2h` (noted in Session Log 2026-07-02 as deliberately left). Verify unreachable via grep for callers, then delete.

> **DONE** (commit `e26c255`). Both re-verified dead: `mrs` was assigned via `db.execute(...).fetchall()` and never read anywhere afterward (superseded by the `mr_rows` query directly below it, per its own "Simpler:" comment). `_get_player_compare_stats`/`_get_h2h` have zero callers anywhere in `app/` — the live `compare()` route computes its stats inline instead. Deleted both.

### 7. Legacy handicap functions caller audit **[LEAD — investigation only]**
`recalc_handicap_for_player`, `recalc_all_for_season` in `handicap.py` predate the chronological rebuild engine. Expected remaining callers: `score_import.py`, `self_report.py`, `api.py` (×4), `migration.py`, and `recalc_season`. Map actual callers; if any function has zero, delete it; if all have callers, record the map in Technical Reference and close this item — do NOT migrate those callers to the rebuild engine (explicitly deferred per Tech Reference).

> **DONE, no code change** (commit `72632ab`). Actual callers matched the expected list exactly — both functions are live, not dead. Concrete file:line map recorded in `4. Technical Reference.md` under "Handicap System — Chronological Rebuild Engine". Callers left untouched per instruction.

## Scope

**In scope:** exactly the items above.

**Out of scope — do not touch:**
- `base.html`'s popover logic beyond adding the shared tooltip helper (item 2).
- Any behavior change to marker *precedence* (item 1 is a pure extraction; output must be bit-identical).
- The UX-consistency territory the cut-off agent never covered (badge vocabulary unification, terminology sweep, mobile view divergence between enter/enter_week, local-style-block consolidation beyond item 3) — that needs its own audit pass; don't freelance it from this document.

## Stop Conditions

- [ ] Item 1: any of the three sites lacks the inputs the shared helper needs, or extraction would change what any site displays. *(Did not fire — all three sites had `round_id`; extraction verified bit-identical.)*
- [x] Item 4: detection requires schema change or expensive per-request computation (see item text) — stop, present options. *(Fired — see item 4 note above.)*
- [ ] Item 6/7: grep shows a live caller for anything this doc calls dead. *(Fired for item 7's two functions — both have live callers, correctly left untouched, no deletion. Did not fire for item 6's two leads — both confirmed genuinely dead, deleted.)*
- [ ] Any item's verification contradicts the finding — skip it, mark it in this file, continue with the rest. *(Did not fire beyond item 4.)*

## Definition of Done

- [x] Each item: fixed, or skipped with a one-line reason recorded under its heading in this file
- [x] `py_compile` on touched .py files; Jinja2 parse on touched templates; brace/paren balance on touched script blocks
- [x] One commit per item (cutoff protocol), pushed to main
- [x] Session Log + Work Packages updated; Status → Complete (or per-item notes if partially done)

## Execution Notes (Sonnet, 2026-07-03)

Executed items 1–3 and 5–7 as fixes; item 4 skipped per its own stop condition (see item 4 note above — needs @user sign-off on a schema addition). One commit per item, pushed directly to `main` after each per this project's documented convention:

| Item | Outcome | Commit |
|---|---|---|
| 1 — `_hcp_marker_map` extraction | Done | `43efdf3` |
| 2 — shared `spTipToggle` | Done | `f05f5b9` |
| 3 — `.hcp-override-dot` promoted | Done | `43bb77e` |
| 4 — crossing-round marker | **Skipped** — stop condition | — |
| 5 — delete `enter_week_backup.html` | Done | `e915b9e` |
| 6 — delete verified-dead Python | Done | `e26c255` |
| 7 — legacy handicap caller map | Done (docs only) | `72632ab` |

**Validation performed:** `python3 -m py_compile` on every touched `.py` file (`scores.py`, `my_stats.py`, `players.py`) — all pass. Jinja2 template-parse (`Environment(loader=FileSystemLoader('app/templates')).get_template(...)`) on every touched `.html` file (`base.html`, `scores/enter.html`, `scores/enter_week.html`, `debug/scoring.html`, `handicap/league_matrix.html`, `handicap/player_history.html`) — all pass. Brace/paren balance checked on every touched inline `<script>` block (custom string-aware scanner, ignoring string/template literals and `//` comments) plus `node --check` on the extracted `base.html` tooltip helper — all balanced. `main.css` brace count symmetric (2261/2261) after the item 3 edit.

**No live DB access in this environment** — items 1–3 and 5–7 are all either pure refactors (no behavior change, verified by direct before/after code comparison) or dead-code removal (verified via grep for callers), so no live-DB spot-check is required for correctness. Nothing in this batch needs a Handicap Rebuild or other data-affecting admin action.

**For @user to visually spot-check post-deploy:**
- Score entry (`enter.html` and `enter_week.html`): the `*` provisional/override marker and the ℹ eligibility-round indicator still show the same tooltip text and position (above the button, flipping below near the top of the viewport) as before.
- Scoring Debug page: the ⚠ absence-mismatch badge tooltip still shows below the badge, flipping above near the bottom of the viewport.
- Handicap Matrix and Handicap History pages: the small amber ✱ override-dot marker still renders identically (same size/color/position) next to overridden handicap values.
- Nothing else changed visually — items 1, 6, 7 are backend-only/docs-only.

## Critical Files

- `app/routes/scores.py` (items 1, 4)
- `app/templates/base.html`, `scores/enter.html`, `scores/enter_week.html`, `debug/scoring.html` (item 2)
- `app/static/css/main.css`, `handicap/league_matrix.html`, `handicap/player_history.html` (item 3)
- `app/templates/scores/enter_week_backup.html` (item 5, delete)
- `app/routes/my_stats.py`, `app/routes/players.py`, `app/routes/handicap.py` (items 6-7)

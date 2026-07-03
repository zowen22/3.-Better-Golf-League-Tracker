# Consolidation & Cleanup Batch (Form/Reuse) — 2026-07-03

**Type:** Audit Finding / Bug Investigation (mixed: verified + leads to verify)
**Status:** Open
**Priority:** P3 (items 1-4), P4 (items 5-7)
**Prepared by:** Fable, 2026-07-03
**Linked WP:** New — Sonnet should add to WP3.1 backlog on pickup

---

## Goal

The duplication that has already caused drift bugs in this codebase is consolidated into shared helpers/classes, and confirmed-dead code is removed. Items marked **[LEAD]** were not fully verified by Fable (audit agents were cut off by session limits) — each has a verification step that must pass before its fix is applied; if verification fails, skip that item and note it, don't improvise.

## Context

General audit (2026-07-03) focused on functionality and form. This codebase's recurring failure mode — documented repeatedly in the Session Log — is copy-drift: near-identical logic pasted per-page, then one copy gets fixed/extended and the others silently rot (popover copies, hcp-marker logic, absolute-vs-differential display duplicates, `.cell-override-dot`). Each item below either removes a dead copy or merges live copies to one source of truth. Items are independent; do them in any order; a failure on one doesn't block the others.

## Findings / Items

### 1. Triplicated `hcp_marker` priority logic — `app/routes/scores.py` **[VERIFIED pattern exists; extraction shape needs confirmation]**
The "manual override beats pre-eligibility provisional" marker computation exists three times: in `enter()`, in `enter_week()`, and in `_load_completed_scorecard()` (which builds `hcp_marker_map` per matchup, ~line 2192-2209 region). All three query `scorecards.hcp_manually_overridden` + `handicap_history` (`trigger_round_id` + `PRE_ELIGIBILITY_MARKER_PREFIX`) and apply the same precedence. This exact duplication already produced one shipped bug (marker missing from the locked view because only the editable-form copy was wired). **Fix:** extract one helper, e.g. `_hcp_marker_map(db, round_id, player_ids) -> {pid: 'override'|'provisional'|None}`, call it from all three sites. Verify each site truly has `round_id` + player ids available before extracting.

### 2. Three click-toggle floating-tooltip JS implementations **[VERIFIED count; consolidation is mechanical]**
Near-identical create-on-first-use + toggle + position + outside-click-dismiss tooltip functions: `showHcpProvTip`/`#hcp-prov-tip` (in BOTH `scores/enter.html` and `scores/enter_week.html`), `ewShowEligTip`/`#ew-elig-tip` (enter.html ~854; check enter_week too), `showAbsMismatchTip`/`#abs-mismatch-tip` (`debug/scoring.html`, added 2026-07-03). **Fix:** one shared `spTipToggle(btn, tipId, text, opts)`-style helper in `base.html` (it already hosts shared popover JS); each page keeps only its text-building line. Keep positioning behavior identical (above-with-flip for the hcp/elig tips, below-with-flip for the mismatch tip — make it an option).

### 3. Duplicated override-dot CSS **[VERIFIED — Fable created the second copy knowingly]**
`.cell-override-dot` (`handicap/league_matrix.html:307-312` local styles) and `.phcp-override-dot` (`handicap/player_history.html` local styles) are the same visual (0.6rem, #f59e0b, super, 1px margin) for the same concept (per-round playing-handicap override). **Fix:** promote one class (suggest `.hcp-override-dot`) to `main.css` next to the `.absent-badge` family; replace both local copies. Check `admin/edit_scores.html` and any other page marking the same concept while at it.

### 4. Retrospective marker gap on eligibility-crossing rounds **[VERIFIED gap; deliberate deferral, now scheduled]**
Since commit `d8da205`, the round that first crosses `min_rounds_for_handicap` is scored with a self-only temp playing handicap, but its `handicap_history` row is real/unmarked (by design — see Tech Reference "Pre-Eligibility Temp Handicap"). Consequence: completed crossing rounds show NO `*` marker in score entry, and on Handicap History the round's Playing Hcp has no visible relationship to its Hcp Index. **Fix (the deferred "Phase 2" from d8da205's plan):** add a third `hcp_marker` value `'crossing'` — detection: round has a real (non-provisional, non-override) `handicap_history` row for `trigger_round_id` AND the player's chronologically-prior real-round count within that timeline equals `min_rounds - 1`… **Stop-condition trigger:** if that detection can't be computed cheaply at display time (it may require walking prior rounds), STOP and propose persisting a marker instead (e.g. a distinct `override_reason` prefix on a *second* row is NOT acceptable — see Tech Reference for why the PRE_ELIGIBILITY prefix must not be reused; a new nullable column or reason-suffix on the real row needs user sign-off).

### 5. Dead file: `app/templates/scores/enter_week_backup.html` **[VERIFIED — zero references]**
Delete it.

### 6. Known dead Python **[LEAD — re-verify each before deleting]**
`my_stats.py` unused `mrs` variable; `players.py` unreachable `_get_player_compare_stats` / `_get_h2h` (noted in Session Log 2026-07-02 as deliberately left). Verify unreachable via grep for callers, then delete.

### 7. Legacy handicap functions caller audit **[LEAD — investigation only]**
`recalc_handicap_for_player`, `recalc_all_for_season` in `handicap.py` predate the chronological rebuild engine. Expected remaining callers: `score_import.py`, `self_report.py`, `api.py` (×4), `migration.py`, and `recalc_season`. Map actual callers; if any function has zero, delete it; if all have callers, record the map in Technical Reference and close this item — do NOT migrate those callers to the rebuild engine (explicitly deferred per Tech Reference).

## Scope

**In scope:** exactly the items above.

**Out of scope — do not touch:**
- `base.html`'s popover logic beyond adding the shared tooltip helper (item 2).
- Any behavior change to marker *precedence* (item 1 is a pure extraction; output must be bit-identical).
- The UX-consistency territory the cut-off agent never covered (badge vocabulary unification, terminology sweep, mobile view divergence between enter/enter_week, local-style-block consolidation beyond item 3) — that needs its own audit pass; don't freelance it from this document.

## Stop Conditions

- [ ] Item 1: any of the three sites lacks the inputs the shared helper needs, or extraction would change what any site displays.
- [ ] Item 4: detection requires schema change or expensive per-request computation (see item text) — stop, present options.
- [ ] Item 6/7: grep shows a live caller for anything this doc calls dead.
- [ ] Any item's verification contradicts the finding — skip it, mark it in this file, continue with the rest.

## Definition of Done

- [ ] Each item: fixed, or skipped with a one-line reason recorded under its heading in this file
- [ ] `py_compile` on touched .py files; Jinja2 parse on touched templates; brace/paren balance on touched script blocks
- [ ] One commit per item (cutoff protocol), pushed to main
- [ ] Session Log + Work Packages updated; Status → Complete (or per-item notes if partially done)

## Critical Files

- `app/routes/scores.py` (items 1, 4)
- `app/templates/base.html`, `scores/enter.html`, `scores/enter_week.html`, `debug/scoring.html` (item 2)
- `app/static/css/main.css`, `handicap/league_matrix.html`, `handicap/player_history.html` (item 3)
- `app/templates/scores/enter_week_backup.html` (item 5, delete)
- `app/routes/my_stats.py`, `app/routes/players.py`, `app/routes/handicap.py` (items 6-7)

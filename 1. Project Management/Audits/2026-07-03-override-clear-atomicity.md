# Override-Clear Routes: Commit-Before-Rebuild Atomicity Gap — 2026-07-03

**Type:** Audit Finding
**Status:** Complete
**Priority:** P2
**Prepared by:** Fable, 2026-07-03
**Linked WP:** Extends WP3.19 (same bug class as the matrix_update atomicity fix); line-item added to WP3.1

---

## Goal

`clear_scorecard_overrides()` and `clear_handicap_override()` (both in `app/routes/handicap.py`) commit their destructive step and the follow-up league rebuild as one unit — or roll back and surface a visible error — matching the atomic pattern already applied to `matrix_update()` in WP3.19.

## Context

WP3.19 (Session Log 2026-07-02, "Ghost Score Correctness") fixed `matrix_update()` because it committed an override *before* attempting the league rebuild/resync, swallowed resync exceptions, and told the admin everything succeeded. The audit that produced this document found the **same pattern survives in the two override-CLEAR routes**, which were not part of that fix.

## Findings

| ID | Finding | Location | Severity |
|----|---------|----------|----------|
| 1 | `clear_scorecard_overrides()`: `UPDATE scorecards SET hcp_manually_overridden = 0 …` then `db.commit()`, THEN `rebuild_league_handicaps_and_scores()` inside `try/except` that only logs (`logging…exception(…)`); success flash (`'Playing handicap overrides cleared.'`) renders unconditionally | `app/routes/handicap.py` ~1051-1082 (function `clear_scorecard_overrides`) | P2 |
| 2 | `clear_handicap_override()`: `DELETE FROM handicap_history …` then `db.commit()`, THEN the same log-only try/except around the rebuild; success flash (`'Manual override cleared and handicap recalculated.'`) unconditional — the message literally claims a recalculation that may have failed | `app/routes/handicap.py` ~1152-1186 (function `clear_handicap_override`) | P2 |

**Failure mechanism (both):** if the rebuild throws, the destructive step is already committed. For (1): flags are 0 but every affected scorecard still holds its old override-derived `handicap_at_time_of_play` — which now *looks like* a legitimately computed value (no flag). For (2): the anchor row is deleted but no regenerated auto row exists and downstream rounds aren't re-derived. Both states are healed by the *next successful* rebuild (flag=0 rows are re-derived unconditionally; the timeline rebuild regenerates deleted auto rows), so this is bounded/recoverable — the real damage is the admin being told it succeeded, so nobody knows to re-run anything.

**Why this is lower stakes than the fixed matrix_update case (still worth fixing):** matrix_update's failure left a *changed handicap* with *unregenerated ghost scores* — active corruption. These two leave *stale-but-plausible* values plus a lie in the flash message.

## Scope

**In scope:**
- Restructure both routes to the exact pattern used by the fixed `matrix_update()` (`app/routes/handicap.py:987-1047` region — read it first and mirror it): perform the destructive step and the rebuild, commit **once** after both succeed; on exception, `db.rollback()` and flash a visible error telling the admin nothing was changed.

**Out of scope — do not touch:**
- `matrix_update()` itself (already correct — it is the reference implementation).
- `rebuild_league_handicaps_and_scores()` / `rebuild_player_handicap_timeline()` internals (they deliberately never commit; caller owns the transaction — that contract is what makes this fix possible).
- The rebuild-preview route `rebuild_timeline()` (its GET rollback behavior is intentional).
- `_process_scores`' post-save rebuild try/except (different tradeoff — a failed rebuild there must NOT roll back the just-saved scores; its warning flash already tells the admin to recalculate manually).

## Implementation Plan

1. Read the fixed `matrix_update()` and copy its transaction/ordering/flash structure.
2. `clear_scorecard_overrides()`: move `db.commit()` to after the rebuild call; wrap both in the try; on exception → `db.rollback()` + `flash('Failed to clear overrides — nothing was changed. Error: …', 'error')` + keep the log line.
3. `clear_handicap_override()`: same restructure; on failure the DELETE is rolled back too, so the override row survives intact (correct — better than a deleted anchor with no rebuild).
4. Validate: `python3 -m py_compile app/routes/handicap.py`.

## Stop Conditions

- [ ] `matrix_update()`'s pattern turns out to differ from what this document describes (re-read it; if the reference itself doesn't commit-once-after-rebuild, stop and ask).
- [ ] Either route turns out to have additional side effects between the destructive step and the rebuild (e.g. notifications) whose ordering matters.
- [ ] The rebuild reliably fails in local testing for an unrelated reason — that's a separate bug; don't paper over it inside this change.

## Definition of Done

- [ ] Both routes commit exactly once, after rebuild success; rollback + error flash on failure
- [ ] `py_compile` passes
- [ ] @user manual check post-deploy: clear a playing-handicap override from the Matrix page and an index override from Handicap History; confirm both still work and show success; (failure path is hard to trigger live — code review suffices)
- [ ] Session Log + Work Packages updated; Status → Complete

## Critical Files

- `app/routes/handicap.py` (`clear_scorecard_overrides`, `clear_handicap_override`; `matrix_update` read-only reference)

---

## Execution Notes (Sonnet, 2026-07-03)

Read `matrix_update()` first (`app/routes/handicap.py:1018-1080`) and confirmed it matches the doc's description exactly: destructive step(s), then rebuild inside `try`, `db.commit()` once after rebuild succeeds, `db.rollback()` + no unconditional success signal on exception. No Stop Conditions fired — mirrored the pattern as planned, no deviations.

**`clear_scorecard_overrides()` (line ~1085):** Removed the `db.commit()` that previously followed the `UPDATE scorecards SET hcp_manually_overridden = 0 ...` statement. That UPDATE and the subsequent `rebuild_league_handicaps_and_scores()` call now share one transaction, committed once after the rebuild succeeds. On exception: `db.rollback()` (new), kept the existing `logging.exception(...)` call, added `flash('Failed to clear overrides — nothing was changed. Error: {e}', 'error')` and an early `return redirect(...)` so the unconditional success flash below is no longer reached on failure.

**`clear_handicap_override()` (line ~1186):** Same restructure. Removed the `db.commit()` that previously followed the `DELETE FROM handicap_history ...`. On rebuild failure, the DELETE now rolls back too — the override row survives intact, which the doc calls out as the correct outcome (better than a deleted anchor with no regenerated auto row). Added the same rollback + error-flash + early-return pattern, kept the existing log line.

No additional side effects (notifications, etc.) were found between the destructive step and the rebuild call in either function, so the "additional side effects" Stop Condition did not apply.

**Validation:** `python3 -m py_compile app/routes/handicap.py` — passes clean.

**Manual check (per Definition of Done, @user):** clear a playing-handicap override from the Matrix page and an index override from Handicap History; confirm both still work and show success. Failure path is hard to trigger live — code review (this document) suffices per the doc's own Definition of Done.

# Mobile Score Entry: Dead Card-View Removal + Table Unification — 2026-07-03

**Type:** Feature Plan (Part 1: dead-code removal; Part 2: UX unification)
**Status:** Draft — DO NOT EXECUTE (user undecided; will flip to Open when ready)
**Priority:** P3 (Part 1), P3 (Part 2)
**Prepared by:** Fable, 2026-07-03
**Linked WP:** New — create WP3.X on pickup

---

## Goal

One mobile scoring experience regardless of entry point, and zero dead scoring UI shipping to browsers. Part 1 deletes the invisible-but-still-executing hole-by-hole card view from `enter.html` (no user-visible change). Part 2 — the actual product decision — gives `enter.html` the same compact `fit()` mobile table `enter_week.html` has, replacing its current plain horizontal-scroll treatment.

## Context

The UX-consistency audit (D1, `2026-07-03-ux-consistency-pass.md`) initially framed this as "two live mobile experiences." Follow-up investigation corrected that: the card view is **visually retired already** — `main.css:4243` hides it unconditionally (`.mobile-sc-section { display: none !important; }`; no media query ever re-shows it; comment on that rule says "retired — full table used on all screen sizes"). What remains is ~85 lines of hidden markup and ~250 lines of controller JS in `enter.html` that still execute on every page load against invisible elements, plus main.css styling for it. The card-view JS is also why `base.html`'s `spApplyAbsenceToScores()` needs a `.mob-score-input` special case.

The *real* mobile variance is table treatment: `enter.html` mobile = desktop table + plain horizontal scroll (`main.css` `@media 768px`, fixed 36px inputs, every column shown); `enter_week.html` mobile = compact table (`@media 640px` local block: canvas-`measureText` dynamic hole widths via `fit()`, Pts/Out/In hidden on entry cards, `--sc-summary-w` shared summary width, abbreviated headers). The week view's treatment received all recent polish investment (scroll-growth fix, column unification) and is the better phone experience; the single-matchup page never got it.

**User is undecided on Part 2 (and chose to hold the whole doc). Do not execute either part while Status is Draft.**

## Scope

**Part 1 — dead card-view removal (no visible change):**
- `enter.html`: delete the `mobile-sc-section` markup block (lines ~375-460, from the `MOBILE SCORECARD` comment through the section's closing div) and the `MOBILE SCORECARD CONTROLLER` script block (lines ~990-1235+ — `allPids`/`hiddenInput`/`mobInput` helpers, `updateDots`, `updateTotals`, `loadHole`, `syncAndCalc`, nav-button wiring, `window.updateMobileView`, the trailing `loadHole(0)` init). Boundaries must be re-verified by exact comment markers at execution time — line numbers drift.
- `enter.html` ~line 822: remove the `if (window.updateMobileView) window.updateMobileView();` call inside `updateAll()` (and any sibling guarded calls to `updateTotals()`/`updateDots()` outside the deleted block — grep first).
- `main.css`: delete the card-view rule family — `.mobile-sc-section` (4243) and the `.mob-*` block (~4261-4415: `mob-progress-*`, `mob-hole-*`, `mob-team-band*`, `mob-player-*`, `mob-score-input`, `mob-nav-*`, `mob-tv-*`, `mob-pt-ind`, `mob-nine-divider` — grep `\.mob-` in main.css for the full set; verify none are used by any OTHER template before deleting: `grep -rl "mob-" app/templates` should hit only enter.html pre-deletion).
- `base.html` `spApplyAbsenceToScores()`: remove the `.mob-score-input` special-case block (comment says "Mobile card view (enter.html)") and the `updateTotals`/`updateDots` fallback calls if they reference only card-view functions — verify `updateTotals`/`updateDots` don't exist elsewhere after deletion (they're defined INSIDE the deleted controller).
- Technical Reference: update the "Mobile layout" paragraph (already describes the planned removal) to past tense.

**Part 2 — table-treatment unification (GATED: separate user go-ahead required even after doc opens):**
- Port `enter_week.html`'s `@media (max-width: 640px)` compact-table CSS block and `fit()` JS to `enter.html`. Prefer extraction over copy-paste given this codebase's copy-drift history: move the media-query CSS to `main.css` under a shared class and the `fit()` function to a shared `<script>` in `base.html` (or a static JS file), parameterized by table selector — `enter.html`'s table already uses the same `sc-col-hole`/`sc-col-name` classes (verified), and `fit()` reads `--sc-summary-w` from `:root`, so the math ports cleanly. `enter_week`-specific bits (`.ew-completed-scorecard` 4-vs-3 summary-column count, `data-mid` scoping) must remain per-page or become parameters.
- Reconcile the 768px vs 640px breakpoint difference (recommend 640px, matching the invested treatment) and remove `enter.html`'s now-redundant plain-scroll rules from the 768px block in main.css (keep `font-size:16px` anti-zoom wherever inputs are styled).

**Out of scope — do not touch:**
- `enter_week.html`'s existing mobile behavior (it is the reference implementation; changes there only if Part 2's extraction requires mechanical refactoring, with zero behavior change).
- The desktop layouts of either page.
- `enter_week_backup.html` (deletion owned by `2026-07-03-consolidation-cleanup-batch.md` item 5).
- Auto-advance/input-type conventions (Tech Reference "Input Advance Philosophy" — unchanged by this work).

## Implementation Plan

1. (Part 1) Re-verify the card view is still unconditionally hidden (`grep -n "mobile-sc-section" app/static/css/main.css` — expect only the `display:none !important` rule). If a media query re-showing it has appeared since, STOP (see Stop Conditions).
2. Delete markup block, controller script, the `updateAll()` hook, main.css `.mob-*` family, and the `spApplyAbsenceToScores` special case, in that order, as ONE commit. Grep `mob-\|updateMobileView\|updateTotals\|updateDots\|loadHole\|syncAndCalc` across app/ afterward — zero hits expected outside `enter_week_backup.html` (dead file) and any unrelated same-named functions (verify by reading context).
3. Validate: Jinja2 parse `scores/enter.html`; brace/paren balance on its remaining script blocks (project-standard check); confirm `spApplyAbsenceToScores` still parses in base.html.
4. (Part 2, only with explicit user go-ahead) Extract-and-share per Scope; one commit for the extraction (enter_week behavior identical), one for enabling it on enter.html.
5. Manual spot-check list for @user: on a phone — enter.html single-matchup entry (scores, auto-advance, absence popover, hcp override input) and enter_week completed + entry cards look/behave unchanged (Part 1) or match each other (Part 2).

## Stop Conditions

- [ ] Status of this document is still `Draft` — do not execute anything.
- [ ] Part 1 step 1 finds the card view is no longer unconditionally hidden (someone re-enabled it since 2026-07-03).
- [ ] Any `.mob-*` class or deleted function name has live references outside `enter.html`/`enter_week_backup.html`.
- [ ] Part 2 attempted without an explicit user go-ahead recorded below this line in this document.
- [ ] Part 2: extraction turns out to require behavior changes to `enter_week.html`'s `fit()` beyond mechanical parameterization.

## Definition of Done

- [ ] Part 1: zero `mob-`/`updateMobileView` references in shipped code; enter.html renders identically before/after on desktop AND mobile (it was already the plain-scroll table on phones)
- [ ] Part 2 (if authorized): both entry pages share one compact-table implementation; single source of truth for the media-query CSS and `fit()`
- [ ] Jinja2 parse + script brace/paren balance on touched templates
- [ ] Session Log + Work Packages updated; this doc's Status → Complete
- [ ] Technical Reference "Mobile layout" paragraph updated to match

## Critical Files

- `app/templates/scores/enter.html` (Parts 1 & 2)
- `app/static/css/main.css` (Part 1 deletion ~4243-4415; Part 2 shared CSS home)
- `app/templates/base.html` (`spApplyAbsenceToScores` cleanup; Part 2 shared `fit()` home)
- `app/templates/scores/enter_week.html` (Part 2 extraction source — behavior must not change)
- `1. Project Management/4. Technical Reference.md` (doc sync)

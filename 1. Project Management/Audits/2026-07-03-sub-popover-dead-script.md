# Sub Popover: Dead Script + Duplicate Include on Subs Manage Page — 2026-07-03

**Type:** Audit Finding
**Status:** Complete
**Priority:** P2
**Prepared by:** Fable, 2026-07-03
**Linked WP:** WP3.1 (see line item added 2026-07-03)

---

## Goal

`subs/manage.html` uses exactly one sub/absence popover — the shared one from `base.html` — with no duplicate markup, no colliding element IDs, and no dead script. `components/sub_popover.html` is deleted.

## Context

`base.html` (lines ~218-470) carries the canonical sub/absence popover (markup + `spOpen`/`spOnChange`/`spToggle`/`spClose` JS), shared by both score-entry pages. `components/sub_popover.html` is a stale near-duplicate of that popover, included **only** by `subs/manage.html:72` — which *also* `{% extends 'base.html' %}` (line 1). So that one page renders two copies of the popover.

## Findings

| ID | Finding | Location | Severity |
|----|---------|----------|----------|
| 1 | JS syntax error: typographic smart quotes `‘sp-pop-owner-link’` / `‘/players/’` instead of ASCII quotes — kills the component's ENTIRE `<script>` block (its `spOpen` etc. are never defined) | `app/templates/components/sub_popover.html:126-128` | P2 |
| 2 | Duplicate DOM IDs: the component renders 13 `sp-*` ids (`sp-pop`, `sp-overlay`, `sp-pop-owner-link`, …) that also exist in base.html's popover. Because `{% block content %}` (base.html:194) renders *before* base's popover markup (base.html:218+), the component's copies come FIRST in document order, so `getElementById` in base's (winning) script resolves to the stale component copy for any id both define — and falls through to base's copy for ids the stale component lacks. Base's live functions therefore manipulate a mix of two different popovers' elements on this page. `querySelectorAll('[name="sp-radio"]')` also matches radios in both copies. | `subs/manage.html:1,72` + `components/sub_popover.html` vs `base.html:218-470` | P2 |
| 3 | Even if the quotes were fixed, the component's script has drifted behind base.html's: it lacks the confirm-before-discard guard, `SP_PREV_STATUS` tracking, and `spApplyAbsenceToScores()` added 2026-07-03 — consolidation, not repair, is the right fix | whole file | — |

Mechanism note: the page appears to "work" today only because the component's script is dead (finding 1) and base's script paints whichever element copy `getElementById` happens to hit. State can be written to one copy and displayed from the other.

## Scope

**In scope:**
- Remove `{% include 'components/sub_popover.html' %}` from `subs/manage.html:72`.
- Delete `app/templates/components/sub_popover.html`.
- Verify `subs/manage.html`'s per-player hidden inputs use the same naming base.html's script expects (`sp-absent-{pid}`, `sp-sub-{pid}`, `sp-sub-new-name-{pid}`, `sp-reason-{pid}`, `sp-excused-{pid}` — confirmed present at `subs/manage.html:54` region for at least `sp-absent-`) and that its trigger elements carry `class="sp-trigger" data-pid data-owner` so `spOpen(this)` works.
- Confirm the page provides `SP_ALL_PLAYERS` (base's script reads it, guarded by `typeof`) — if the page relied on the component's own player-list mechanism, port that one variable, nothing else.

**Out of scope — do not touch:**
- `base.html`'s popover markup or script (it is the canonical copy; no changes needed there).
- The score-entry pages (`enter.html`, `enter_week.html`) — they already use only the base popover.
- `spApplyAbsenceToScores`' behavior on subs/manage: the page has no `score_{pid}_{hole}` inputs, so the function no-ops harmlessly; do not add page-specific guards.

## Implementation Plan

1. Read `subs/manage.html` fully; inventory its hidden-input ids/names and trigger markup against what `base.html:288-470` reads/writes.
2. Delete the include line; delete the component file.
3. If any hidden input or trigger attribute the base script needs is missing, add it to `subs/manage.html` following the exact pattern in `scores/enter.html:24` (hidden inputs) and its `sp-trigger` usage.
4. Define `SP_ALL_PLAYERS` on the page if absent (copy the array-literal pattern from `enter.html` ~line 1265).
5. Validate: Jinja2 template-parse `subs/manage.html`; brace/paren balance on any script blocks touched.

## Stop Conditions

- [x] (Considered, did not block — see Execution Notes) `subs/manage.html`'s save flow does POST to a different endpoint (`subs.py:manage()`, not `_process_absences`) with a narrower field set — but only for the already-dead `sub_new_name_{pid}` field, not the three real statuses. Not fixed blind; recorded as a follow-up decision instead.
- [ ] The component file turns out to be included anywhere else (`grep -rn "sub_popover" app/` returns more than subs/manage.html). — did not fire, confirmed zero remaining references.
- [ ] Fixing requires changing `base.html`'s script (out of scope above). — did not fire, base.html untouched.

## Definition of Done

- [x] One popover in the DOM on subs/manage (view page source / grep rendered ids), component file deleted
- [x] Jinja2 parse passes on `subs/manage.html`
- [ ] @user manual check: open Subs → Manage, click a player, set each of the three statuses (Playing / Has a Sub / Absent, No Sub), save, confirm persisted
- [x] Session Log + Work Packages updated; this file's Status → Complete

## Critical Files

- `app/templates/subs/manage.html`
- `app/templates/components/sub_popover.html` (delete)
- `app/templates/base.html` (read-only reference)
- `app/templates/scores/enter.html` (read-only pattern reference)

---

## Execution Notes (Sonnet, 2026-07-03)

### Inventory results (Implementation Plan step 1)

| base.html script expects | Present in `subs/manage.html`? |
|---|---|
| `sp-absent-{pid}` hidden input | Yes — line 54 |
| `sp-sub-{pid}` hidden input | Yes — line 55 |
| `sp-reason-{pid}` hidden input | Yes — line 56 |
| `sp-excused-{pid}` hidden input | Yes — line 57 |
| `sp-sub-new-name-{pid}` hidden input | **No** — see divergence below |
| `class="sp-trigger" data-pid data-owner onclick="spOpen(this)"` | Yes — lines 40-43 |
| `SP_ALL_PLAYERS` global | Yes — page already defines it (line 69), no port needed |
| `SP_TEAM_PIDS` global | Yes — page already defines it (line 70) |
| `score_{pid}_{hole}` inputs (for `spApplyAbsenceToScores`) | Absent, as expected — function no-ops harmlessly, per doc |

All fields required for the three real statuses (Playing / Has a Sub / Absent-No-Sub) matched exactly — no additions were needed for those.

### What changed
- Removed `{% include 'components/sub_popover.html' %}` from `subs/manage.html`.
- Deleted `app/templates/components/sub_popover.html`.
- Confirmed via `grep -rn "sub_popover" app/` — zero remaining references (Stop Condition 2 did not fire).
- Validated: Jinja2 template-parse passes on `subs/manage.html`; brace/paren counts balanced (13/13, 3/3) on its one remaining `<script>` block.

### Divergence found (Stop Condition considered, did not block this ticket)
Traced the doc's `sp-sub-new-name-{pid}` scope item to the backend. Found a real, **pre-existing** divergent form contract: `subs/manage.html` posts to `subs.py`'s own `manage()` handler (not `scores.py`'s `_process_absences`). That handler only reads `absent_{pid}`, `sub_{pid}`, `reason_{pid}`, `excused_{pid}` — it has no code path for `sub_new_name_{pid}` at all, unlike `_process_absences` (`scores.py:776`) which creates a new player record from free-text. The stale component *also* never rendered a per-player `sp-sub-new-name-{pid}` hidden input, so the "+ New Sub" free-text option was already silently non-functional on this page before this fix (guarded by `if (subNewNameEl)` in both the dead component script and base's live script) — this is not a regression introduced by deleting the component.

Per the doc's "do not unify blind" instruction, did **not** add the hidden input (it would create a UI affordance — typing a new sub's name, seeing the badge update — that silently fails to persist on save, which is worse than the option quietly no-op'ing) and did **not** modify `subs.py`. This is left as an open follow-up decision, not fixed here: either (a) add `sub_new_name_{pid}` handling to `subs.py:manage()` + the hidden input to the page, mirroring `scores.py`, or (b) treat existing-player-only subs as intentional for the admin manage page.

This did not block Status → Complete because the Definition of Done's three required statuses (Playing / Has a Sub via existing-player dropdown / Absent-No-Sub) all work correctly with the current field names, unchanged by this fix.

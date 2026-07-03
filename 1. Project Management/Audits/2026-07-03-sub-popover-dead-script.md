# Sub Popover: Dead Script + Duplicate Include on Subs Manage Page — 2026-07-03

**Type:** Audit Finding
**Status:** Open
**Priority:** P2
**Prepared by:** Fable, 2026-07-03
**Linked WP:** New — Sonnet should add to WP3.1 backlog on pickup

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

- [ ] `subs/manage.html`'s save flow turns out to POST to a different endpoint with different field names than `_process_absences` expects (i.e. the stale popover was load-bearing for a divergent form contract) — stop and show the user the divergence instead of unifying blind.
- [ ] The component file turns out to be included anywhere else (`grep -rn "sub_popover" app/` returns more than subs/manage.html).
- [ ] Fixing requires changing `base.html`'s script (out of scope above).

## Definition of Done

- [ ] One popover in the DOM on subs/manage (view page source / grep rendered ids), component file deleted
- [ ] Jinja2 parse passes on `subs/manage.html`
- [ ] @user manual check: open Subs → Manage, click a player, set each of the three statuses (Playing / Has a Sub / Absent, No Sub), save, confirm persisted
- [ ] Session Log + Work Packages updated; this file's Status → Complete

## Critical Files

- `app/templates/subs/manage.html`
- `app/templates/components/sub_popover.html` (delete)
- `app/templates/base.html` (read-only reference)
- `app/templates/scores/enter.html` (read-only pattern reference)

# UX Consistency Pass (Form) — 2026-07-03

**Type:** Audit Finding
**Status:** Complete (2026-07-03, Sonnet)
**Priority:** P3 (items A, B, D), P4 (item C)
**Prepared by:** Fable, 2026-07-03
**Linked WP:** WP3.1 (line item added on completion)

---

## Goal

Same concept → same rendering, league-wide: one status-badge definition, one matchup-status visual, one handicap column label, and a user-decided single mobile scoring experience. Companion to `2026-07-03-consolidation-cleanup-batch.md` (which owns tooltip-JS and override-dot consolidation — do not re-do those here).

## Context

Completes the UX-consistency audit pass that was cut off by session limits during the 2026-07-03 general audit. Sweeps run by Fable directly (badge vocabulary, terminology, table classes, empty states, mobile divergence, tooltip mechanisms). Empty-state usage (52 templates on `.empty-state`) and click-tooltip pages were checked and are healthy or already covered — omitted below.

## Findings

| ID | Finding | Location | Severity |
|----|---------|----------|----------|
| A1 | `.status-badge` defined TWICE in main.css with conflicting palettes: first block (line 449) scheduled=blue/completed=green; second block (line 581) scheduled=green/completed=gray. Cascade means the second silently wins; the first is a dead trap — editing it does nothing. | `main.css:449-460` vs `main.css:581-592` | P3 |
| A2 | Matchup-status concept rendered two unrelated ways: `.status-badge--completed`/`--in_progress` (main.css) vs `.ew-completed-badge`/`.ew-inprogress-badge`/`.ew-notentered-badge` (local trio) — same information, different look per page. | `main.css:581-592` vs `scores/enter_week.html:512-514` | P3 |
| A3 | `.dbg-badge` copy-pasted into three debug templates (one already drifted: scoring.html's is one-line-minified with different margin). | `debug/migration_audit.html:173`, `debug/scoring.html:222`, `debug/scorecards.html:126` | P4 |
| A4 | Generic-named `.badge-warning`/`.badge-provisional` defined locally in one template — names imply a shared system that doesn't exist; invisible to other pages wanting the same. | `handicap/player_history.html:245-246` | P4 |
| A5 | Modifier naming: `--in_progress` (snake_case) vs kebab-case everywhere else (`--fun-night`, `--bye-week`). Cosmetic; fix only if touching A1/A2 anyway (requires updating emitters). | `main.css:460,591` | P4 |
| B1 | Playing-handicap column header: **"Hdcp"** in ~20 templates (dominant), "Playing Hcp" (`dashboard.html`, `handicap/player_history.html`), "HCP" (`registration/admin_queue.html:35`, `stats/course_stats.html:74`), "Playing HCP" (`schedule/detailed_score_sheet.html:60`). Same number, four labels. | listed | P3 |
| B2 | User-facing noun split: badges/notes say "Provisional" (consistent, good) but eligibility/marker tooltip prose says "temporary handicap". Pick one noun in member-visible text ("provisional" recommended — it's the badge). | `base.html`/`scores/enter*.html` tooltip strings vs badge copy | P4 |
| C1 | `<table class="table">` (×2) — matches no stylesheet rule (`.table` is not defined in main.css); these render as unstyled default tables. Find via `grep -rn '<table class="table"' app/templates`. | 2 templates | P4 |
| C2 | `.records-table` (9 uses) is a full parallel table style alongside the standard `.data-table` (25 uses + variants). Possibly deliberate (leaderboard look); confirm with user before any merge — otherwise leave. | `main.css:4003+`, records templates | P4 |
| D1 | **Mobile scoring experience fork:** `scores/enter.html` still ships the hole-by-hole mobile card view (`#mobile-sc-section`, `mob-*` ids, `loadHole()` — live code at lines 377-460+), while `scores/enter_week.html` uses the compact scrollable table with JS `fit()`. Technical Reference ("Score Entry — Input Advance Philosophy") claims the card view is "retired" — the doc and the code disagree. Two different phone experiences for the same task depending on entry point. | `enter.html:377+` vs `enter_week.html` mobile CSS; Tech Ref §"Mobile layout" | P3 |

## Scope

**In scope:**
- A1: delete one `.status-badge` block (USER DECISION: which palette — see Stop Conditions); grep all `status-badge--` emitters to confirm intended colors.
- A2: replace the `ew-*-badge` trio with `status-badge` + modifiers (add a `--not_entered`/`--not-entered` modifier to main.css); keep the 🔒/🔓 emoji text.
- A3: promote one `.dbg-badge` to main.css, delete the three locals.
- A4: rename to `.hh-badge-warning`/`.hh-badge-provisional` OR promote to main.css if A2's work wants them — implementer's choice, state it in the commit.
- B1: standardize compact column headers on **"Hdcp"** (the 20-file majority); the two "HCP" and one "Playing HCP" headers change to "Hdcp"; "Playing Hcp" on `player_history.html` STAYS (that page distinguishes Playing Hcp vs Hcp Index side-by-side — the long label is load-bearing there); `dashboard.html`'s "Playing Hcp" → implementer judgment by available width.
- B2: change "temporary handicap" → "provisional handicap" in the member-visible tooltip strings (grep `temporary handicap` in templates); leave `PRE_ELIGIBILITY_MARKER_PREFIX` and admin settings copy untouched (internal/admin, and the marker string is load-bearing — see Tech Reference).
- C1: change `class="table"` → `class="data-table"` on both, visually sanity-check via template context.
- D1: **fix the Technical Reference doc only** (correct the "retired" claim to describe reality: card view live on enter.html, compact table on enter_week.html). Do NOT delete or unify the card view — that's a product decision (see Stop Conditions).

**Out of scope — do not touch:**
- Tooltip-JS consolidation and override-dot CSS (owned by `2026-07-03-consolidation-cleanup-batch.md` items 2-3).
- `components/sub_popover.html` (owned by `2026-07-03-sub-popover-dead-script.md`).
- `enter_week_backup.html` (dead file, deletion owned by cleanup batch item 5).
- `.records-table` merge (C2 — investigate/ask only).
- Any behavioral change to the mobile card view or `fit()` table.

## Implementation Plan

1. A1 first (foundation): read both blocks + every `status-badge` emitter; apply user's palette decision; delete the loser.
2. A2 on top of A1; A3, A4, C1 independently, any order.
3. B1/B2 as one "terminology" commit (pure copy changes).
4. D1 doc correction in Tech Reference.
5. One commit per item-group (cutoff protocol), `py_compile`/Jinja-parse validation per project standard.

## Stop Conditions

- [ ] A1: before deleting either block, ask the user which palette is correct (blue-scheduled or green-scheduled) — Fable did not determine which pages visually rely on the current (second-block) rendering. Present both with where they appear.
- [ ] A2: if any `ew-*-badge` carries behavior (JS hooks/selectors), not just style — grep for the class names in script blocks first.
- [ ] B1: if any "HCP"-labeled column turns out to show a hole's handicap-index rank (course data) rather than a player's playing handicap — those are different concepts; `stats/course_stats.html:74` is suspect (sits next to Par) — verify what it renders before relabeling; hole-rank columns should NOT say "Hdcp".
- [ ] D1: if the user, when asked, wants the mobile experiences unified rather than documented — that's a new design task; stop after the doc fix and report.

## Definition of Done

- [ ] One `.status-badge` definition; one matchup-status visual; zero `dbg-badge` locals; no bare `class="table"`
- [ ] Column-label grep shows "Hdcp" as the only compact header variant (excluding player_history's deliberate long labels and any confirmed hole-rank columns)
- [ ] Tech Reference mobile-layout paragraph matches shipped reality
- [ ] Jinja2 parse on touched templates; visual spot-check list for @user in the session log
- [ ] Session Log + Work Packages updated; Status → Complete

## Execution Notes (Sonnet, 2026-07-03)

- **A1**: Pre-resolved by user decision (bypassing the stop condition below) — kept the second/winning block (scheduled=green/completed=gray, the currently-rendered palette), deleted the first (dead) block. Zero visual change.
- **A2**: No JS hooks found on `ew-completed-badge`/`ew-inprogress-badge`/`ew-notentered-badge` (grepped app-wide). Replaced with `.status-badge` + new `--not_entered` modifier; kept snake_case to match the existing `--in_progress` convention (did not also do A5's kebab-case cleanup — out of scope, cosmetic-only per the finding).
- **A3**: All three `.dbg-badge` locals were pixel-identical (only formatting differed); promoted one copy to main.css.
- **A4**: Renamed to `.hh-badge-warning`/`.hh-badge-provisional` (local rename, not promoted — colors aren't reused elsewhere).
- **B1**: `stats/course_stats.html:74` **SKIPPED** — verified via template context (sits in a `<th>Hole</th><th>Par</th><th>HCP</th>` row) that this is a per-hole handicap-rank/stroke-index column, not a player's playing handicap. Stop Condition fired as anticipated; left as "HCP". All other B1 relabels (admin_queue.html, detailed_score_sheet.html, dashboard.html) completed.
- **B2**: All member-visible "temporary handicap" occurrences in templates changed to "provisional handicap" (9 files). No admin-settings-page occurrences were found by the grep, so nothing was excluded on that basis.
- **C1, D1**: Completed as specified, no deviations.

## Critical Files

- `app/static/css/main.css` (A1, A2, A3 promotion)
- `app/templates/scores/enter_week.html` (A2)
- `app/templates/debug/migration_audit.html`, `debug/scoring.html`, `debug/scorecards.html` (A3)
- `app/templates/handicap/player_history.html` (A4)
- B1/B2/C1: ~6 templates from the Findings table (`registration/admin_queue.html`, `stats/course_stats.html`, `schedule/detailed_score_sheet.html`, `dashboard.html`, plus the two bare-`table` templates found by grep)
- `1. Project Management/4. Technical Reference.md` (D1)

# Score Entry Process Audit — 2026-06-12

**Type:** Process Audit  
**Status:** Open  
**Priority Summary:** P0 (5 flow/UX) · P1 (4 data integrity) · P2 (4 validation) · P3 (4 polish) · P4 (3 edge cases)  
**Linked WP:** Phase 5 — Score Entry Audit Remediation  
**Audited By:** Claude (Explore agent, 2026-06-12)  
**Key Files:** `app/routes/scores.py`, `app/templates/scores/enter.html`, `app/routes/self_report.py`, `app/schema_postgres.sql`

---

## Executive Summary

The score entry system is functionally complete and the core calculations (net scoring, match-play points, Stableford) are correct. However, the entry **flow has meaningful friction** that adds 4–6 unnecessary clicks per session, and there are **moderate data integrity gaps** around transaction handling and duplicate prevention. None of the P0–P1 issues cause data loss under normal operation, but they create risk under error conditions and slow down the most-used admin workflow.

---

## Findings

### P0 — Entry Flow / UX *(fix first — most-used workflow)*

| ID | Finding | Location | Status |
|----|---------|----------|--------|
| P0-1 | Course & Tee not pre-set on matchup creation → forces 4 extra clicks + 2 full-page reloads before scorecard appears | `scores.py:228-229`, `enter.html:99-129` | **Fixed** |
| P0-2 | Absence form is a **separate POST** (`save_absences` action) — admin must save absences *before* entering scores or subs aren't reflected in scorecard | `scores.py:272-296`, `enter.html:18-92` | **Fixed** |
| P0-3 | Course/Tee dropdowns trigger `reloadForm()` POST twice — 2-3 second full page reload each time before scorecard renders | `enter.html:104, 117` | **Fixed** |
| P0-4 | No pre-submit validation indicator — admin fills all 36–72 holes, hits Save, then gets an error flash if one hole is empty; no inline warning | `scores.py:531-541` | **Fixed** |
| P0-5 | Mobile scorecard (hole-by-hole pagination) adds ~17 extra Next-button clicks vs desktop; auto-advance on last player's score helps but doesn't eliminate it | `enter.html:371-445` | Open |

**Click-count baseline (worst path, no course/tee pre-set):** 42–78 clicks  
**Click-count target (course/tee pre-set + combined absence form):** 38–74 clicks  
**Quick win:** Pre-setting Course+Tee at matchup creation time eliminates the two form reloads entirely.

---

### P1 — Data Integrity

| ID | Finding | Location | Status |
|----|---------|----------|--------|
| P1-1 | `_process_scores()` commits all round data first, then runs handicap recalc. If recalc throws, round data is committed but handicaps are stale with no error surface | `scores.py:~685` | Open |
| P1-2 | No unique constraint on `rounds(matchup_id)` — admin can re-submit the same matchup, creating duplicate rounds and polluting handicap history | `schema_postgres.sql` | Open |
| P1-3 | `player_absences.round_id` is backfilled *after* the round row is created. If anything fails between these two steps, absence records become orphaned (linked to matchup but no round) | `scores.py:652-658` | Open |
| P1-4 | Per-player tee selection is allowed but not validated against the matchup's course — admin could select a tee from a different course, causing mismatched hole handicaps silently | `scores.py:508`, `enter.html:255-264` | Open |

---

### P2 — Validation

| ID | Finding | Location | Status |
|----|---------|----------|--------|
| P2-1 | `league_settings.max_score_per_hole` column exists in schema but is **never read or enforced** in `_process_scores()` — the setting is orphaned | `schema_postgres.sql:~130`, `scores.py:520-542` | Open |
| P2-2 | Null `holes.handicap_index` silently returns 0 strokes from `strokes_on_hole()` — no warning logged; course data corruption goes undetected until scores look wrong | `scores.py:49-50` | Open |
| P2-3 | Self-report enforces 1–15 per hole; admin direct entry allows 1–20 (HTML5). Scores are copied from self-report to rounds on approval without re-validation | `self_report.py:181`, `enter.html:274-275` | Open |
| P2-4 | `scoring_mode` is referenced in score calculation (`settings['scoring_mode']`, `scores.py:551`) but the column likely doesn't exist in `league_settings` schema — Stableford mode feature is half-baked | `scores.py:551`, `schema_postgres.sql:~104-141` | **Fixed** |

---

### P3 — Audit Trail / UX Polish

| ID | Finding | Location | Status |
|----|---------|----------|--------|
| P3-1 | Direct admin entry saves `scorecards.approved=1` with no `approved_by_user_id` — no record of who entered scores (self-report approval does track this) | `scores.py:~636` | Open |
| P3-2 | Client-side live calc uses JS arrays (`HOLE_HCP`, `HOLE_PARS`) that are loaded from the selected tee; server independently recalculates. If the wrong tee was loaded in JS, displayed points won't match saved points — silent mismatch | `enter.html:543-710`, `scores.py:562-606` | Open |
| P3-3 | Two admins submitting simultaneously: the second admin silently redirects (matchup.status='completed'); no error message explaining why | `scores.py` (status check block) | Open |
| P3-4 | "Allow double-digit scores" checkbox (`enter.html:148-150`) is hidden/undiscoverable; user preference isn't persisted across sessions — admin has to re-enable every session | `enter.html:148-150`, `scores.py` JS section | Open |

---

### P4 — Edge Cases

| ID | Finding | Location | Status |
|----|---------|----------|--------|
| P4-1 | If admin enters scores directly AND a self-report is later approved for the same matchup, the approval flow could create a second round row (duplicate) | `self_report.py` approval handler | Open |
| P4-2 | Cascade-delete behavior when a course or tee is deleted after scores have been entered is undocumented — foreign key handling unknown | `schema_postgres.sql` FK definitions | Open |
| P4-3 | `players.starting_handicap = NULL` → `calc_playing_handicap()` returns 0.0 → player effectively plays scratch with no warning to the admin | `scores.py:25-26` | Open |

---

## Files Referenced

| File | Purpose |
|------|---------|
| `app/routes/scores.py` | Main score entry route, `_process_scores()`, absence handling |
| `app/templates/scores/enter.html` | Entry form — 1079 lines; course/tee dropdowns, scorecard, mobile view |
| `app/routes/self_report.py` | Member score submission + admin approval flow |
| `app/routes/admin.py` | `edit_scores()` / `_save_edited_scores()` for completed rounds |
| `app/routes/score_import.py` | CSV bulk import (admin-only) |
| `app/schema_postgres.sql` | `rounds`, `scorecards`, `hole_scores`, `match_results`, `league_settings` |

---

## Fix History

| Finding | Fix Summary | Commit |
|---------|-------------|--------|
| P0-1 | Added Course+Tee dropdowns to `edit_matchup` form (GET loads options, POST saves them); score entry route already reads `matchup['course_id']`/`tee_id'` as defaults | `6fcab36` |
| P0-2 | Unified absence section inside main score-form; removed separate `absence-form` POST and "Save Absences" button; backend already processed inline absences, moved block before tee validation so absences save even without tee | `6fcab36` |
| P0-3 | Added `GET /scores/tees-json/<course_id>` endpoint; course dropdown now AJAX-populates tee options without page reload; tee change uses GET redirect (`?course_id=X&tee_id=Y`) instead of form POST; route reads `request.args` on GET | `c3569e3` |
| P0-4 | `validateScores()` checks all `.score-input` elements pre-submit; highlights missing cells with red outline (`.score-cell-missing`); shows inline count message; on mobile navigates to first missing hole; clears on input | `c3569e3` |
| P2-4 | Added `scoring_mode TEXT NOT NULL DEFAULT 'match_play'` to `schema_postgres.sql`; rewrote `migrate_scoring_mode.py` for Postgres; fixed `admin.py` settings save from broken `:name` SQLite syntax to `%(name)s` psycopg2 syntax; removed silent-failure fallback block | `8c7b7bc` |

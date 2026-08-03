# PM Docs — Structure & Staleness Audit

**Type:** Meta / Process Audit
**Status:** Complete — "Fix first" items (1-4) actioned 2026-08-01; "Worth doing this/next session" (5-7) and "Optional polish" (8-11) all actioned 2026-08-03 (see Session Log).
**Prepared by:** Sonnet (fork), 2026-07-31
**Linked WP:** N/A — meta/process audit

-----

## Ask

@user: "Perform an audit on our PM docs and supporting documentation as well as structure. I'd like to ensure the tree is very sensible and the contained documentation is up to date." Full read of `1. Project Management/` (all 7 top-level files, `Audits/`, `Handoffs/`, `Orchestration/`, `Plans/`, `Artifacts/`), cross-checked against `CLAUDE.md`'s documented structure and against the actual shipped-work record in Work Packages/Session Log/GLT Feature Parity. Findings-only — nothing moved, renamed, deleted, or silently corrected.

-----

## Axis 1: Structure Sensibility

### 1.1 — CLAUDE.md's documented structure is behind what the project actually has

`CLAUDE.md`'s "Framework Structure" section documents exactly 5 files (`1. Problem Statement.md` through `5. Session Log.md`). The project has grown two more top-level files that aren't mentioned there at all: `6. PM Template Improvement Suggestions.md` and `7. GLT Feature Parity.md`. Both are referenced *elsewhere* in CLAUDE.md (the "PM Improvement Suggestions" section names file 6 explicitly) or are clearly load-bearing (file 7 is 686 lines, actively maintained), so this isn't dead weight — it's real growth CLAUDE.md's own structure section never caught up to. Same gap for `Orchestration/` (a real, coherent Planner/Executor process folder, referenced by name in CLAUDE.md's "Orchestration Handoffs" section) and now `Artifacts/` (see 1.3). Not a defect in the files themselves — a defect in CLAUDE.md's own "Framework Structure" list being stale relative to CLAUDE.md's *own other sections*.

### 1.2 — `Plans/` and `Handoffs/` each have a `README.md` explaining scope/lifecycle; `Audits/` and `Artifacts/` don't

`Plans/README.md` and `Handoffs/README.md` both open with a one-paragraph purpose statement, lifecycle, and naming convention. `Audits/` has never had one (checked — no `README.md` in the directory), despite being the folder CLAUDE.md gives the most explicit standing instruction about ("Check `1. Project Management/Audits/` for any files with `Status: Open`..."). Worth the same 10-line README the other two folders already have, for consistency and because Audits/ status values in practice are messier than CLAUDE.md's own two documented values (see 1.4).

### 1.3 — `Artifacts/` (new, this session) has no cross-reference anywhere else in the PM tree

Confirmed via grep across all 5 numbered top-level files: zero mentions of `Artifacts/` outside the folder itself. It holds 3 real files (mobile nav options, theme palette options, GLT stats-parity reference — all archived copies of claude.ai-hosted design artifacts) but nothing in `4. Technical Reference.md` or `5. Session Log.md` points a future session at it, and it has no README stating what it's for or when to add to it (contrast with 1.2). A future session has no way to discover this folder exists except by directory listing. Low-cost fix: one line in Technical Reference or a README matching the Plans/Handoffs pattern.

### 1.4 — `Audits/` Status values have drifted beyond CLAUDE.md's documented two

CLAUDE.md says to check for `Status: Open` or `Status: In Progress`. In practice, the 14 files in `Audits/` use six different values: `Open`, `Complete`, `OBSOLETE`, `Planned`, and two long free-text variants that embed a status *and* a running commentary in the same field (e.g. `2026-07-03-league-creation-new-season-audit.md`'s status line is a full paragraph). This isn't necessarily wrong — the free-text ones are informative — but it means a mechanical "grep for Status: Open" (which is literally what CLAUDE.md instructs) will miss real open items phrased as `Planned` and won't distinguish `Complete` from the two genuinely-still-open `Open` audits (see 2.1). Same drift, smaller scale, in `Plans/`: CLAUDE.md's documented lifecycle is `Evaluating → Decision: [chosen approach] → Archived`, but in practice a fourth de-facto stage — `Ready to build` — is used across ~10 files and is never mentioned in CLAUDE.md at all (see 2.2, the bigger finding).

### 1.5 — One naming-convention outlier in `Plans/`

`Plans/assets-2026-07-16-landing-draft.html.txt` breaks the `YYYY-MM-DD-slug.md` pattern every other file in `Audits/`, `Handoffs/`, and `Plans/` follows (date-first, `.md` extension). It's a supporting asset for `2026-07-16-ui-overhaul.md`, not a plan doc itself, which explains why it doesn't fit the pattern — but as named it reads like a stray file, not an intentional attachment. A `Plans/assets/` subfolder (matching how `Handoffs/` and `Audits/` stay flat but this is a different kind of content) or at minimum a rename to `2026-07-16-landing-draft-assets.html.txt` would make the association obvious without opening it.

### 1.6 — Orchestration/ is fine as-is

Two files (`Orchestration Instructions.md`, `Handoff Template.md`), clearly scoped, directly referenced by name from CLAUDE.md's "Orchestration Handoffs" section. No finding here — included only because the task asked whether it's "a vague catch-all," and it isn't.

-----

## Axis 2: Content Staleness / Accuracy

### 2.1 — Two of four "Open" audits are stale; their linked work is already shipped

- **`Audits/2026-06-12-score-entry-audit.md`** — `Status: Open`, dated 7 weeks ago. Its linked WP section, `Phase 5: Score Entry Audit Remediation` (`3. Work Packages.md:387-420`), shows **WP5.0 through WP5.3 fully complete** (every `@claude` checkbox checked) and WP5.4 has exactly one item left, tagged `@user` not `@claude` (`P4-2: Review cascade-delete FK behavior... in Supabase dashboard`). This audit should read `Complete — one @user-owned follow-up remaining (P4-2)`, not `Open`.
- **`Audits/2026-07-04-dashboard-widget-visibility-investigation.md`** — `Status: Open — findings ready for Fable to plan from`. The feature it scoped (member-dashboard widget toggles) **shipped the same day**, confirmed at `3. Work Packages.md:101`: `SHIPPED to main 2026-07-04 (861f2df)`, which explicitly cites this audit file as its own "Investigation:" source. Nothing in this audit's stated scope remains unbuilt — it should read `Planned → Shipped 2026-07-04`, not `Open`.

**Not stale, but worth a status-text clarity fix:** `Audits/2026-07-04-site-admin-dashboard-investigation.md` also reads `Status: Open`, but here it's *substantively* still true — v1 shipped 2026-07-06 (`Handoffs/2026-07-06-site-admin-dashboard-v1.md`), and the WP entry (`3. Work Packages.md:466`) explicitly says "Bigger v2 questions... tracked in `Audits/2026-07-04-site-admin-dashboard-investigation.md`, not blocking." The doc's own header just doesn't say "v1 shipped, v2 questions still open" — as written it reads identically to the actually-stale one above, which is confusing on its own.

### 2.2 — 12 Plan docs from the 2026-07-09/07-10 stats-parity pass were never moved to `Archived`, despite being fully built

CLAUDE.md's Plans lifecycle: `Evaluating → Decision: [chosen approach] → Archived`, and explicitly: "archive the plan file [when resolved]." The plan docs below still carry non-terminal status text (`Ready to build`, `Decision: build X`, or `In Progress`) even though `7. GLT Feature Parity.md`'s own "Build Status Summary" (`7. GLT Feature Parity.md:650-665`, dated "refreshed 2026-07-10") and `3. Work Packages.md`'s session-history line both independently confirm every one of them is **built and shipped**:

- `2026-07-09-best-ball-format-question.md` — "Implementation underway"; actually shipped (Best Ball/Team Totals/Classical Stroke Play all live)
- `2026-07-09-contests-report-and-leaderboards.md` — "Ready to build"; shipped (Contest Winners report, 4 tabs)
- `2026-07-09-hall-of-fame.md` — "Decision: build Approach B"; shipped
- `2026-07-09-league-scoring-leaderboard.md` — "Decision: build as a standalone page"; shipped (`/stats/leaderboard`)
- `2026-07-09-player-participation-report.md` — "Decision: build, visible to all members"; shipped (`/stats/participation`)
- `2026-07-09-player-scoring-detail-enhancements.md` — "Decision: build #1 and #4..."; shipped
- `2026-07-09-player-season-comparison.md` — "Decision: compare gross/net/handicap average"; shipped (`/stats/player-compare`)
- `2026-07-09-weekly-recap-redesign.md` — "Decision: Approach A + B..."; shipped per Session Log
- `2026-07-10-contest-winners-technical-spec.md` — "Ready to build"; shipped
- `2026-07-10-hall-of-fame-technical-spec.md` — "Ready to build"; shipped
- `2026-07-10-leaderboard-and-comparison-technical-spec.md` — "Ready to build"; shipped
- `2026-07-10-player-participation-technical-spec.md` — "Ready to build"; shipped
- `2026-07-10-scoring-formats-technical-spec.md` — "In Progress... Building Phase 0 → Phase 3"; shipped

(For contrast, the two **Declined** plans from the same pass — `2026-07-09-course-handicap-reference.md`, `2026-07-09-standings-position-trend.md` — correctly say `Declined... Archived`. The convention is known and followed for declines; it just wasn't applied to the built ones.)

Also worth noting: `Ready to build` is used as a de-facto fourth lifecycle stage across this whole batch and isn't in CLAUDE.md's documented three-stage lifecycle at all — either CLAUDE.md should acknowledge it (log as a PM Template Improvement Suggestion — see 2.6) or these should skip straight to `Decision:` per the documented convention.

**Not stale — correctly reflects real partial completion:** `2026-07-16-ui-overhaul.md` (`In Progress`) and `2026-07-28-mobile-nav-and-theme-options.md` (`Nav: Archived · Themes: Evaluating`) both genuinely have unfinished phases per Work Packages' own text (Phase 4/5 of the UI overhaul explicitly deferred; theme options explicitly still under @user review as of this session). Included here only to show the check was applied evenly, not to flag either as a problem.

### 2.3 — `Work Packages.md`'s progress counter is off: states 325/360, actual count is 322/358

Counted directly (`grep -c "\[x\]"` / `"\[ \]"` across the whole file): **322 checked, 36 unchecked = 358 total**, not the 360 the header claims, and 322 checked not 325. Minor drift (3 tasks), consistent with the counter being hand-incremented in the session-history narrative rather than recomputed from the actual checkbox count each time.

### 2.4 — `7. GLT Feature Parity.md`'s own top-of-doc status table contradicts its own later content

Line 13's Part 4 summary row reads: `**Open, not started** — access confirmed working (2026-07-09), site map inventoried below, no content reviewed yet.` But the same document, further down, has a fully populated and dated `### Build Status Summary (refreshed 2026-07-10 — single source of truth...)` at line 650 showing 13 Built, several Declined, and the rest resolved — directly contradicting "no content reviewed yet." This is a self-contradiction within one file, not a cross-file drift — whoever refreshed the Build Status Summary section on 2026-07-10 didn't scroll back up to fix the line-13 status row.

### 2.5 — `4. Technical Reference.md` has a natural home for this week's tee-system work, and it's silent there

Last dated update inside the file: 2026-07-27. It already has a `## Tee Deduplication` section (line 232) covering the `tees` table's color/nine/gender dedup logic — the exact neighborhood where this week's additions belong. Grepped the whole file for `SETTING_HELP`, `matchup_tee_overrides`, `preferred_tee_name`, `week_summary_latest`, and `Admin Quick Options` — **zero matches for all five.** None of the following (all built and shipped this week per Session Log) are documented: the Site Wiki's `SETTING_HELP`-as-source-of-truth convention, `matchup_tee_overrides` (incl. `tee_id_2` hybrid support), the course-default → `preferred_tee_name` → matchup-override resolution hierarchy (and its known inconsistency across `enter()`/`enter_week()`/`print_scorecards()`), the Admin Quick Options widget restructuring, or `schedule.week_summary_latest()`. CLAUDE.md's own rule: "Keep Technical Reference.md current as decisions are made."

### 2.6 — `2. Project Overview.md`'s Decisions Log stops at 2026-07-28

14 entries, most recent dated 2026-07-28 (mobile nav pattern choice). Nothing from this week's genuinely decision-shaped work: the "tee choice auto-remembers by default, no opt-in checkbox" reversal (explicitly logged as superseding a prior session's decision in `5. Session Log.md`'s 2026-07-30 entry), the wiki settings-vs-freeform-content source-of-truth convention, or the Fairway Drench "background matches the header's exact dark green" decision from today. CLAUDE.md: "Promote significant decisions to Decisions Log in Project Overview.md."

### 2.7 — `6. PM Template Improvement Suggestions.md`: 2 of 7 suggestions are already implemented in CLAUDE.md but not marked resolved; a 3rd is superseded

- **Suggestion #2** ("Add Memory vs PM Files Rule") — its exact proposed section now exists verbatim as `## Memory vs PM Files` in the live `CLAUDE.md`. Still listed here as an open suggestion.
- **Suggestion #7** ("Add PM Improvement Suggestion Process to CLAUDE.md") — its exact proposed rule now exists as `## PM Improvement Suggestions` in the live `CLAUDE.md`. Still listed here as open.
- **Suggestion #1** ("Clarify Session Start Routine") — the friction point (ambiguous "check if files have been shared" phrasing) no longer exists in CLAUDE.md's actual Session Start Routine, which now reads "Read `3. Work Packages.md`, `5. Session Log.md`, and any open Audits/, Plans/, or Handoffs/ files..." — not the exact wording suggested, but the friction is resolved. Superseded, not literally adopted verbatim.

This file has no mechanism to mark a suggestion as adopted (no `[Resolved]` state, unlike what it itself proposes for its hypothetical `Known Issues.md` in suggestion #3) — worth adding one, if only to itself.

Suggestions #3 (Known Issues/Bug Log), #4 (audit-to-WP-task ID cross-referencing), #5 (archive old Session Log entries), and #6 (track iOS work in WP) remain genuinely unaddressed. **#5 in particular has become more relevant, not less, since it was written**: `5. Session Log.md` is now 3,913 lines, and `3. Work Packages.md`'s top progress line is a single multi-thousand-word run-on paragraph spanning the entire project history (visible directly at the top of the file) — both are close to the exact symptom #5 was written to prevent.

### 2.8 — No `STARTED`-without-`COMPLETED` Session Log entries found

Checked every `Status:` marker in `5. Session Log.md` (19+ entries) — all read `COMPLETED`, none left `STARTED`. No interrupted-session flag needed. The top `[CHECKPOINT]` line is substantively still accurate (theme options genuinely remain the oldest open item) but is timestamped `2026-07-29` even though a full additional session (`2026-07-30`) has since completed below it without the checkpoint being refreshed — minor currency lag, not a factual error.

### 2.9 — `Handoffs/` are all clean

All 6 dated Handoffs read `Status: Done`. None sitting `Open` or `Blocked` — nothing to surface.

-----

## Recommendations, Prioritized

**Fix first (concrete, low-effort, actively misleading if left):**
1. Flip the 2 stale `Audits/` statuses (2.1) — `score-entry-audit` → Complete, `dashboard-widget-visibility-investigation` → Shipped.
2. Archive the 12 built-and-shipped `Plans/` docs (2.2) — mechanical, ~5 min, directly fixes CLAUDE.md-compliance.
3. Fix `7. GLT Feature Parity.md` line 13's self-contradicting status row (2.4) — one line.
4. Recompute `Work Packages.md`'s progress counter (2.3) — trivial once the count is known: **322/358**.

**Worth doing this session or next (real content gaps, moderate effort):**
5. ✅ **Done 2026-08-03.** Added the missing Technical Reference section for this week's tee-override/wiki/admin-panel work (2.5) — "Per-Player Tee Resolution & Matchup Overrides", "Site Wiki — `SETTING_HELP` Source of Truth", "Admin Quick Options Widget".
6. ✅ **Done 2026-08-03.** Backfilled the 3 missing Decisions Log entries (2.6) — tee auto-remember reversal, wiki source-of-truth convention, Fairway Drench background decision.
7. ✅ **Done 2026-08-03.** Marked suggestions #1/#2/#7 resolved in the PM Template Improvement Suggestions file; also implemented #5 (Session Log archiving) rather than just considering it — file had grown to 4,042 lines/128 sessions, well past the suggestion's own ~10-session threshold. Older sessions moved to new `5. Session Log Archive.md`.

**Optional polish (structure, no urgency):**
8. ✅ **Done 2026-08-03.** Added `README.md` to `Audits/` and `Artifacts/`, matching `Plans/`/`Handoffs/` (1.2, 1.3).
9. ✅ **Done 2026-08-03.** Cross-referenced `Artifacts/` from Technical Reference and `7. GLT Feature Parity.md` so all 4 files are discoverable (1.3).
10. ✅ **Done 2026-08-03.** Renamed `Plans/assets-2026-07-16-landing-draft.html.txt` → `Plans/2026-07-16-landing-draft-assets.html.txt` (1.5).
11. ✅ **Done 2026-08-03.** Logged CLAUDE.md's stale "Framework Structure" list as suggestion #9 in the PM Template Improvement Suggestions file (1.1) — not edited directly, per CLAUDE.md's own rule that template changes go through the Suggestions file.

**Fine as-is:** `Orchestration/` (1.6), `Handoffs/` (2.9), Session Log `STARTED` hygiene (2.8), the `Declined`/`Archived` plans and the two genuinely-still-in-progress ones (2.2) — all checked and correct, included for completeness.

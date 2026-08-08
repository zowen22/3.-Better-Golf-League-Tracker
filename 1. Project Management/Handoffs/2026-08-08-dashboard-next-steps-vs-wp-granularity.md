# Handoff: Project Dashboard "Next Steps" Preview vs. Work Packages Detail/Granularity

*Status: `Open`*
*Created: 2026-08-08 — Planner: Sonnet (local BGLT session)*
*Priority: `Medium` — Effort: `M`*
*Depends on: `None`*
*Parallel-safe: `Yes` — doesn't touch BGLT application code*

-----

> This handoff is written for the agent @user has scoped to the Project Dashboard
> repo, the PM template repo (`X.-Claude-Project-Framework`), and the rest of the
> GitHub org — not for a normal BGLT executor session. The problem and a first
> attempted fix both surfaced inside BetterGolfLeagueTracker, but @user was explicit
> that the actual solution must be decided and implemented at the template/dashboard
> level, consistently across every project that shares this PM framework — not as a
> BGLT-specific patch. The exact strategy is intentionally left open below; @user's
> words: "that's up to the agent."

## Goal

Make the Project Dashboard's per-project "next steps" preview reliably show short,
accurate action items — without forcing Work Packages files (in this or any sibling
project) to sacrifice the rich, detailed logging they currently carry for completed
(and often open) tasks. Whatever the fix is, it needs to work the same way across
every project on this GitHub that uses the shared PM template, not just BGLT.

## Context

**How the dashboard currently reads a project** (from BGLT's `CLAUDE.md`, "Project
Dashboard Compatibility" section — this same section was added to both BGLT's live
CLAUDE.md and the template repo's CLAUDE.md directly, per a 2026-08-03 session,
since it was judged a template-level change):
- Reads `2. Project Overview.md`'s `## Status` / `## Summary` directly from `main`,
  unauthenticated.
- Reads `3. Work Packages.md`'s checkboxes for a progress bar, and pulls the **first
  5 unchecked `- [ ]` lines, in file order**, verbatim, as the "next steps" preview.

**The rule that's supposed to keep that safe** already exists in CLAUDE.md's Rules
section: *"Keep Work Packages task items to one clear verb phrase, ≤60 characters —
detail belongs in Technical Reference or Session Log."*

**What happened (2026-08-08, BGLT):** @user asked why BGLT's dashboard card was
showing prose instead of action items. Root cause: two of the first five unchecked
`- [ ]` lines in BGLT's `3. Work Packages.md` were 422 and 598 characters — full
paragraphs with embedded rationale and status notes, not verb phrases. Direct
violation of the rule above.

**This is not a two-line slip.** A file-wide measurement of BGLT's Work Packages
found:
- 98% of checked (`- [x]`) items exceed 60 characters (avg. ~346 chars)
- 97% of unchecked (`- [ ]`) items exceed 60 characters (avg. ~312 chars)

The ≤60-char rule has essentially never been enforced in this project. Work Packages
has functioned for months as a rich changelog-with-rationale, not a scannable task
list — and that appears to be a genuinely useful, load-bearing pattern for resuming
work cold, not accidental drift (see Findings below). Whether the same pattern holds
in sibling projects (`1.-Autonomous-UAVs`, `6.-Curriculum-Tool`, `8.-Magic-Band`, and
others using this template) hasn't been checked — worth confirming as part of this
work, since it changes how urgent/widespread the fix needs to be.

**First attempted fix (built, then reverted same session):** Trimmed BGLT's two
offending open items to one-line pointers and relocated their full context into
`7. GLT Feature Parity.md` — a doc that tracks BGLT's feature comparison against a
competitor product. @user's objection, verbatim reasoning: that file is a
BetterGolfLeagueTracker-specific artifact — it doesn't exist in the template and
doesn't exist in sibling projects on this GitHub. Anchoring the fix there means the
solution only works for BGLT and can't be applied consistently across the PM system.
That fix was reverted (commit `77eb7dc`, reverting `613d9c6`) rather than kept as a
one-off. A PM Improvement Suggestion documenting this same root-cause analysis
(numbered #11) was logged and then also reverted along with it — the analysis below
supersedes that entry; no action needed on it, it no longer exists in the file.

## Findings / Evidence

- Dashboard behavior (first-5-unchecked-lines, verbatim) is documented in BGLT's
  `CLAUDE.md` under "Project Dashboard Compatibility" — confirm this still matches
  the dashboard's actual fetch/parse code in `X.-Claude-Project-Dashboard`; don't
  assume the CLAUDE.md description is perfectly in sync with the live implementation.
- BGLT's own measurement command (reproducible against any project's Work Packages
  file):
  ```
  python3 -c "
  lines = open('1. Project Management/3. Work Packages.md').readlines()
  checked = [l for l in lines if l.strip().startswith('- [x]')]
  unchecked = [l for l in lines if l.strip().startswith('- [ ]')]
  def avg(ls): return sum(len(l) for l in ls)/len(ls) if ls else 0
  def over60(ls): return sum(1 for l in ls if len(l) > 60)
  print(f'checked: {len(checked)}, avg {avg(checked):.0f}, over60 {over60(checked)}')
  print(f'unchecked: {len(unchecked)}, avg {avg(unchecked):.0f}, over60 {over60(unchecked)}')
  "
  ```
- Worth noting for design purposes: **only unchecked lines are ever surfaced
  externally** by the dashboard. Checked items' length never reaches it. Any fix that
  requires trimming/relocating *all* historical content (not just open items) is
  doing more work than the dashboard problem actually demands — but may still be
  worth doing for other reasons (that's a judgment call for this agent, not a given).
- The rich-detail-on-completed-items pattern seems to be a genuine productivity
  asset, not just noise: across 300+ completed BGLT Work Packages entries spanning
  months, the inline detail lets a session resume a task cold without cross-
  referencing Session Log or Technical Reference. A solution that requires
  scrubbing that down to bare phrases sitewide would likely be a net productivity
  loss for @user, independent of the dashboard question.

## Scope

### In
- A convention and/or mechanism, defined at the template level (`X.-Claude-Project-
  Framework`'s CLAUDE.md and/or the dashboard's own parsing logic), that keeps the
  dashboard's next-steps preview short and accurate.
- Applying/validating that convention against BGLT's real Work Packages content as
  a live test case (its current 113–114 lines are back to their original
  422/598-char prose — a real, unresolved example to design against).
- Checking whether the same violation pattern exists in sibling projects, to gauge
  how much of this is "fix the rule" vs. "fix the rule and also backfill several
  repos."

### Out
- Do not resurrect the BGLT-specific `7. GLT Feature Parity.md` relocation as *the*
  general solution. It may still be a reasonable place for BGLT's own detail once a
  general convention exists (e.g. if the convention is "put overflow detail in
  whatever doc already owns the topic, project-specific or not"), but the mechanism
  itself must not depend on every project inventing its own bespoke tracking doc.
- Do not assume all sibling projects need immediate backfilling — confirm scope
  first; @user may want to handle rollout project-by-project, similar to how the
  2026-08-03 session left "backport CLAUDE.md's Dashboard Compatibility section to
  sibling repos" as an open @user decision rather than doing it unilaterally.

## Implementation Plan

This is a design task, not a pre-decided implementation — @user explicitly wants
this agent's judgment on strategy, not a prescribed sequence. Some candidate
directions worth evaluating (not a ranked recommendation):

1. **Delimiter convention** — e.g. `- [ ] @claude - Short headline — full detail...`
   and teach the dashboard to display only the text up to the first em-dash/pipe as
   the "next step." Detail stays in place, no relocation needed anywhere, and it's
   mechanically enforceable (a session can check "is there a delimiter within the
   first ~70 chars" rather than "is the whole line short").
2. **Separate next-steps surface** — a small, hand-maintained list (new template
   file, or a `## Next Steps` block atop Work Packages) that the dashboard reads
   instead of raw checkboxes. Decouples "what should a human/dashboard see right
   now" from "the full task ledger."
3. **Dashboard-side smarter truncation** — display first N chars + ellipsis, or
   truncate at the first sentence boundary. Lowest effort, but doesn't really fix
   the underlying convention, just hides the symptom.
4. Something else this agent judges better after actually reading the dashboard's
   parsing code and a sample of Work Packages files across the org — the above are
   starting points, not constraints.

Whatever direction is chosen, update it in the template's CLAUDE.md (Rules section
+ Project Dashboard Compatibility section) as the canonical source, not just in a
single project's Suggestions file.

## Stop Conditions

- If the chosen strategy requires editing a project's *live* CLAUDE.md directly
  (not just the template), that's an explicit precedent-following exception (see
  2026-08-03 session, "Project Dashboard Compatibility" section) — confirm with
  @user before doing it to BGLT or any other individual project, don't assume it's
  automatically authorized by this handoff.
- If backfilling sibling projects' existing Work Packages content turns out to be
  necessary for the fix to actually work (not just "nice to have"), stop and confirm
  scope/priority with @user before touching repos beyond BGLT and the template.
- Don't guess at the dashboard's actual fetch/parse implementation — read
  `X.-Claude-Project-Dashboard`'s source directly before designing around assumed
  behavior; the CLAUDE.md description of it may be stale.

## Definition of Done

- [ ] A convention/mechanism is decided and documented in `X.-Claude-Project-
      Framework`'s canonical CLAUDE.md (not only in a single project's files)
- [ ] BGLT's dashboard next-steps preview shows 5 clean, accurate items again,
      verified against the live dashboard
- [ ] BGLT's `1. Project Management/3. Work Packages.md` lines 113–114 (currently
      still the original long-form entries) are resolved under the new convention
- [ ] A decision is recorded on whether/how sibling projects need to adopt the same
      convention (backport now, or flag for @user later — either is fine, but the
      decision itself should be explicit, not silently skipped)

## Critical Files

| File | Why |
|------|-----|
| `X.-Claude-Project-Framework` CLAUDE.md | Canonical template copy of the Rules + Project Dashboard Compatibility sections — the real fix belongs here |
| `X.-Claude-Project-Dashboard` (fetch/parse source — exact path not yet located by this session) | May need updating if the chosen convention changes what counts as a displayable "next step" |
| `BetterGolfLeagueTracker/CLAUDE.md` | This project's live copy of the same sections — needs to stay in sync with the template once resolved |
| `BetterGolfLeagueTracker/1. Project Management/3. Work Packages.md` | Live example of the violation (lines 113–114), to validate the new convention against |

-----

## Execution Report

*Filled in by the executor.*

*Executed: [date] — Executor: [model/session]*

### What Was Done

-

### Deviations from Plan

-

### Follow-ups Discovered

-

# Handoff: Project Dashboard "Next Steps" Preview vs. Work Packages Detail/Granularity

*Status: `Done`*
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

- [x] A convention/mechanism is decided and documented in `X.-Claude-Project-
      Framework`'s canonical CLAUDE.md (not only in a single project's files)
- [~] BGLT's dashboard next-steps preview shows 5 clean, accurate items again,
      verified against the live dashboard — verified against a reference
      implementation of the shipped algorithm, **not** by loading the live page
      (see Deviations); @user should eyeball the card once Pages redeploys
- [x] BGLT's `1. Project Management/3. Work Packages.md` lines 113–114 (currently
      still the original long-form entries) are resolved under the new convention
      — resolved *without editing them*, which is the point of the chosen approach
- [x] A decision is recorded on whether/how sibling projects need to adopt the same
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

*Executed: 2026-08-08 — Executor: Sonnet (local session, PM/template scope)*

### What Was Done

**Chosen strategy: shorten at display time, change no Work Packages content.**
The dashboard now derives a short headline from each item instead of printing the
line verbatim. Nothing in any project's Work Packages file was edited, and no
project lost any detail.

Measured first, across all 9 dashboard-listed repos, because the handoff's framing
suggested a systemic problem. It isn't — it's concentrated in 3 repos. Average open
item length: Golf-Shot-Dispersion 54, Resume 65, UAVs 67, Curriculum 71,
Zach-Owen 76 — all fine as-is; Magic-Band 155, High-Ground-Coffee 135, BGLT 305.
So the fix had to avoid regressing the 6 healthy repos, which ruled out anything
that reformats content globally.

`X.-Claude-Project-Dashboard` @ `71ac171` — reworked `parseNextSteps`:
1. Skips sections whose heading marker says `*(COMPLETE)*` / `*(PAUSED …)*` /
   `*(SKIPPED …)*` / `*(Deferred)*`; `*(In Progress)*` always wins. This is what
   fixes Magic-Band, whose paused RF work was outranking live work.
2. Still takes the last 5 remaining unchecked items in file order.
3. Renders headline only — ≤95 chars verbatim, longer lines cut at the first
   ` — ` / ` -- ` / `: ` after dropping markdown and short parentheticals, else
   truncated at 90. Also dedupes repeats and escapes HTML.

`X.-Claude-Project-Framework` @ `b6fc7d6` — retired the ≤60-character rule and
replaced it with a front-load-the-headline rule; rewrote the Project Dashboard
Compatibility section to describe the above; added the companion rule that heading
markers must be kept accurate, since they're now load-bearing.

Result on this project's two named lines, with no edit to either:
- line 113 (422 chars) → `@user/@claude - Workflow Parity continuation`
- line 114 (598 chars) → `@claude - New idea, not yet scoped`
- the 4,483-char UI/UX overhaul item → `@claude - UI/UX overhaul`

5 of 9 repos produce byte-identical output to before — nothing was broken there,
so nothing changed.

### Deviations from Plan

- **The handoff's own premise was partly stale.** It states the dashboard pulls the
  *first* 5 unchecked lines. The live code has taken the *last* 5 since 2026-08-05
  (`c184f40`), and the template CLAUDE.md was corrected then. BGLT's local CLAUDE.md
  still says "first 5" — that stale copy is what the handoff was written from.
- **Candidate direction 2 (separate next-steps surface) was proposed by @user and
  declined after discussion.** It duplicates rather than derives, so it goes stale
  silently and costs a parallel edit on every WP change in 9 repos.
- **The phase-aware ordering idea (Findings/Implementation Plan) was prototyped and
  rejected on evidence.** Preferring "the most-advanced phase with any checked
  items" made 5 of 9 repos *worse* — it surfaced Phase-1 setup tasks
  (Golf-Shot: "Create Xcode project"; High-Ground-Coffee: "Turn off storefront
  password protection") over genuinely current work, because completed WPs routinely
  retain unchecked stragglers. File-order recency plus explicit heading markers beat
  it on every repo tested. Recorded in the template's PM Improvements Processed Log
  so it isn't re-proposed.
- **Stop Condition honored:** editing live project CLAUDE.md files was put to @user,
  who chose "template only, sync later." No sibling CLAUDE.md was touched —
  including this project's, which therefore still documents the old ≤60-char rule
  and the stale "first 5" behavior.
- **Could not verify against the live dashboard.** No JavaScript runtime exists in
  this environment (no node/deno/bun), so the ported JS was never executed. It was
  verified by a line-equivalent Python mirror committed at
  `X.-Claude-Project-Dashboard/test/next-steps-reference.py`, with a snapshot of
  expected output for every project. Mitigation: headline extraction is wrapped in
  try/catch that falls back to the raw line, so a defect degrades to today's
  behavior rather than blanking the cards. **@user should still eyeball the page.**

### Follow-ups Discovered

- **Sibling CLAUDE.md sync is outstanding** (deferred by @user). 8 repos still carry
  the old rule text. Tracked in the template repo's
  `1. Project Management/PM Improvements/Processed Log.md`.
- **`11.-Resume` and `12.-Zach-Owen.com` are private.** Both have valid PM files and
  parse correctly, but the dashboard fetches unauthenticated, so they cannot be
  added to `PROJECTS` until they're public. Same blocker as the existing
  `10.-Personal-Finances` item on the dashboard's own backlog — worth one decision
  covering all three rather than three separate ones.
- **Plain language is still an authoring behavior, not a parser guarantee.** The
  derivation makes items short and accurate; it cannot make them jargon-free.
  "Revisit migrating auth to Supabase Auth" is short and still opaque to a cold
  reader. If the executive-summary reading level matters, that has to come from how
  the headline is written — which is what the new template rule asks for, at no
  extra token cost since the line is being written anyway.
- **Magic-Band has a genuine duplicate** — "Confirm ornament shell interior
  dimensions to set board outline target" appears as two separate open items in
  different WPs. The dashboard now dedupes it at display time, but the underlying
  duplication is real and should be cleaned up in that project.

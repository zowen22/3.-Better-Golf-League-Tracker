# Fable → Sonnet Handoff Template

Fable does the brainstorm, design, implementation planning, and orchestration.
Sonnet picks up the resulting document in a **separate session with no shared
context** and executes it. Everything Sonnet needs to act correctly — and to
know when *not* to act — must be in the document. Sonnet should not need to
re-derive a decision Fable already made, and should not guess past a point
Fable flagged as a decision point.

Copy this template for each audit finding, review, or design task Fable
produces. One document per independently-executable unit of work — don't
bundle unrelated fixes into one handoff just because they were found in the
same audit pass (see "Splitting work" below).

Save to `1. Project Management/Audits/<YYYY-MM-DD>-<short-slug>.md`. This is
the folder Sonnet already checks at the start of every session per
`CLAUDE.md`'s Session Start Routine — a handoff with `Status: Open` is picked
up automatically, no separate index needed.

---

## Template

```markdown
# <Task Name> — <YYYY-MM-DD>

**Type:** Audit Finding / Design Review / Feature Plan / Bug Investigation
**Status:** Open
**Priority:** P0–P4 (P0 = correctness/security/data-integrity, P4 = polish)
**Prepared by:** Fable, <date>
**Linked WP:** <existing Work Package this extends, or "New — Sonnet should
  create WP3.X on pickup">

---

## Goal

One to three sentences. What does "done" look like? State the *outcome*, not
the steps — Sonnet derives steps from the Implementation Plan below, but
needs the goal to sanity-check that the steps still add up to the right
thing partway through.

## Context

Why this exists. What prompted the audit/review, what problem or risk it
addresses. A fresh session has none of the conversation that led here —
write as if briefing someone who wasn't in the room.

## Findings

*(Audit/review tasks only — omit for a greenfield design task.)*

The evidence. Concrete, falsifiable, with exact locations:

| ID | Finding | Location | Severity |
|----|---------|----------|----------|
| 1  | <what's wrong, one line> | `file.py:123-140` | P0/P1/P2/P3 |

Include *why* it's wrong, not just what — a symptom without a mechanism
forces Sonnet to re-investigate before it can safely fix anything, which
defeats the point of Fable having already done that work.

## Scope

**In scope:**
- Explicit list of what Sonnet should change.

**Out of scope — do not touch:**
- Explicit list of adjacent things that might look related but aren't part
  of this task. This is the single highest-leverage section for preventing
  scope creep across a context-free handoff — a fresh session with no
  memory of *why* something was left alone will "fix" it unless told not to.

## Implementation Plan

Ordered, concrete steps. Reference existing functions/files/patterns to
reuse by name and location — Sonnet should not need to search the codebase
to discover something Fable already found. Where a step has more than one
reasonable approach, state which one Fable chose and why, so Sonnet doesn't
re-litigate it.

1. ...
2. ...

## Stop Conditions

Sonnet must stop and ask the user (not guess, not proceed) if any of the
following occur. Be specific to this task — generic conditions like "if
unsure" are not actionable; a condition should be something Sonnet can
check against concretely while executing.

- [ ] Any step above turns out to require a decision Fable didn't already
      make explicit (e.g. the plan assumed X but the code actually does Y)
- [ ] Fixing a Finding would require touching a file listed in "Out of
      scope"
- [ ] A schema/migration change turns out to be needed that this document
      didn't already plan for
- [ ] Evidence found during execution contradicts a Finding above (the bug
      isn't there, or isn't what this document says it is)
- [ ] <task-specific condition — e.g. "the fix would change what gets
      counted toward match points, not just gross-score stats">

## Definition of Done

- [ ] Every item in Scope is addressed; nothing in "Out of scope" was
      touched
- [ ] Validated per the project's standard no-live-DB pattern: `py_compile`
      on touched `.py` files, Jinja2 template-parse on touched `.html`
      files (see `4. Technical Reference.md`)
- [ ] <task-specific verification — e.g. a worked-example calculation, a
      manual spot-check for @user to run post-deploy>
- [ ] Session Log entry added; Work Packages updated; this file's `Status`
      changed to `Complete` (or `Blocked` with a note, if a Stop Condition
      fired) and, if `Complete`, moved into the relevant WP as normal —
      the standalone file can stay as the historical record

## Critical Files

List every file Sonnet will touch. If the pattern repeats across many
files, describe the pattern once and list representative paths — don't
enumerate every occurrence if there are more than ~10.
```

---

## Splitting work

One handoff document per independently-executable, independently-stoppable
unit. If Finding 3 depends on Finding 1 landing first, they can share a
document (sequence them in the Implementation Plan) — but if they're
unrelated fixes that happened to surface in the same audit pass, give them
separate documents. A Stop Condition firing on one shouldn't block Sonnet
from picking up the other.

## What Fable should NOT put in these documents

- Speculative "might also want to" scope — that belongs in
  `6. PM Template Improvement Suggestions.md` or a separate backlog note,
  not inside a document meant to be executed as-is.
- Anything requiring Fable's own judgment mid-execution that isn't resolved
  into a concrete instruction. If Fable can't decide between two approaches,
  that indecision itself is a Stop Condition to hand to the user — not
  something to leave implicit for Sonnet to resolve.

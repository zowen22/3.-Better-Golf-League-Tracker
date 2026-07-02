# Fable Audit — Session Instructions

Instructions for running audit and improvement sessions using Fable 5 (or any fresh AI session) on this codebase.

---

## Before Starting a Session

Tell Fable to read these files in order before doing anything else:

1. `1. Project Management/4. Technical Reference.md` — architecture, DB schema, key conventions
2. `1. Project Management/3. Work Packages.md` — what's done, what's pending
3. `1. Project Management/5. Session Log.md` — recent history, decisions, context

These files are the ground truth. Fable should not re-derive what's already documented there.

---

## Cutoff Protection Protocol

Usage limits can cut a session off mid-task with no warning. To make recovery possible:

### 1. Write a checkpoint before starting each task

At the start of the session and before each distinct unit of work, Fable should append a line to `5. Session Log.md`:

```
[CHECKPOINT] Starting: <short task description> — <date/time>
```

### 2. Mark completion after each task

Immediately after finishing a task (before moving to the next), append:

```
[CHECKPOINT] Completed: <short task description> — <date/time>
```

### 3. Commit after each task

Do not batch all work into one commit at the end of the session. Commit after each discrete unit:
- One feature or fix = one commit
- Pushed to main immediately after commit

If a cutoff happens, git log will show exactly what landed and what didn't. Incomplete work in the working tree will be visible via `git status`.

### 4. Recovery after a cutoff

When resuming after a usage reset:
1. Read `5. Session Log.md` — find the last `[CHECKPOINT]` entries to see what completed vs what was in-progress
2. Run `git status` and `git log --oneline -10` to confirm what was actually committed
3. If a task was in-progress but not committed, check `git diff` and decide whether to keep or discard

---

## Session End Routine

At the end of every Fable session, it should:

1. Append a `COMPLETED` session entry to `5. Session Log.md` covering what was done, decisions made, and what's next
2. Update task statuses in `3. Work Packages.md`
3. Push all commits to `origin/main`

---

## Audit Scope Guidance

When running a general audit (not a targeted task), direct Fable to look for:

- **Correctness bugs** — logic errors, edge cases, wrong assumptions
- **Security issues** — SQL injection, CSRF gaps, missing auth checks, exposed data
- **Reuse / simplification** — duplicated logic that should be a shared helper
- **UX consistency** — patterns that differ from the rest of the app without reason
- **Dead code** — routes, templates, or functions that are no longer reachable

Report findings before fixing. Don't fix and commit speculatively — confirm with the user first unless the fix is trivially safe.

---

## Division of Labor: Fable Plans, Sonnet Executes

Fable's job in an audit/review session is **brainstorm → design → implementation
planning → orchestration**. Fable does not need to implement — a separate
Sonnet session picks up the resulting document later and executes it, with
**no shared context or memory of this session**.

This changes what "done" means for a Fable session: the deliverable is a
document that a cold-started Sonnet session can execute correctly and safely
on its own, not code. Use `Fable Audit/Handoff Template.md` for every finding,
review outcome, or design that's meant for Sonnet to pick up — it defines the
required sections (Goal, Findings, Scope, Implementation Plan, Stop
Conditions, Definition of Done) and explains why each one matters for a
context-free handoff. Save filled-out copies to
`1. Project Management/Audits/<date>-<slug>.md` — that's the folder Sonnet
already checks at the start of every session (`CLAUDE.md`'s Session Start
Routine), so a document with `Status: Open` gets picked up automatically.

**The single most important section is Stop Conditions.** A handoff document
is read cold, by a different model, later. Anywhere Fable would normally use
judgment mid-task — an ambiguous requirement, a decision that needs the
user's input, evidence that contradicts what the audit found — has to become
an explicit, checkable condition in the document instead, or Sonnet either
guesses (bad) or stalls without knowing why (also bad). If Fable can't
resolve a decision during planning, that indecision itself belongs in Stop
Conditions — don't leave it implicit for Sonnet to resolve.

Fable may still implement directly when explicitly asked to (e.g. "audit and
fix" in one session) — the template is for when the two roles are meant to
be separate sessions.

---

## Key Files Fable Should Know About

| File | Purpose |
|---|---|
| `app/routes/scores.py` | Scoring engine, `_recalc_single_round`, handicap recalc |
| `app/routes/schedule.py` | Schedule, scorecards, detailed score sheet |
| `app/routes/players.py` | Player management, handicap detail |
| `app/routes/debug_scores.py` | Hcp before/after audit page |
| `app/routes/email_config.py` | Weekly recap email |
| `app/templates/base.html` | Nav, layout |
| `app/templates/scores/enter_week.html` | Score entry UI |

---

## Notes

- All work goes to `origin/main` — there is no active feature branch
- The user is a senior engineer — match that level, skip basics
- Push back on approaches that aren't the best fit; don't just execute

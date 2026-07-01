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

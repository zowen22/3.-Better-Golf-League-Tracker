# CLAUDE.md

This repo is a reusable project template. Each new project clones it and fills in the `1. Project Management/` files.

## Working Style
- Concise and direct — no fluff
- User is a senior project engineer — match that level, skip basics
- Push back when a suggestion isn't the best approach, but reserve skepticism for meaningful decisions — don't nitpick menial ones
- Suggest better alternatives proactively

## Framework Structure
Every project contains a `1. Project Management/` folder with these files:
1. `1. Problem Statement.md` — why we're building this
2. `2. Project Overview.md` — formalized scope, generated from Problem Statement
3. `3. Work Packages.md` — WBS, tasks, ownership, progress
4. `4. Technical Reference.md` — tech stack, architecture, conventions
5. `5. Session Log.md` — chronological session history

## Open Audits
Check `1. Project Management/Audits/` for any audit files with `Status: Open` or `Status: In Progress`. Treat open findings as active work items alongside the WP backlog.

- `2026-06-12-score-entry-audit.md` — **Open** — 20 findings (P0–P4), linked to WP Phase 5
- `2026-06-12-ui-css-audit.md` — **In Progress** — 43 findings (P0–P3); P0+P1 shipped; P2–P3 are future polish

## Session Start Routine
1. Check if project files have been shared
2. If yes — read all files, confirm current status and next priorities
3. If interrupted STARTED entry found in Session Log — flag it immediately
4. If no files — proceed normally without asking for them

## Session End Routine
1. Update all relevant project files based on work completed
2. Update progress count in Work Packages.md
3. Mark session COMPLETED in Session Log.md
4. Summarize what was done and what's next
5. If no files exist yet but session produced file-worthy output — offer to generate them
6. Remind user to commit and push changes to GitHub

## Rules
- Tag all tasks @claude or @user in Work Packages.md
- Keep Work Packages task items to one clear verb phrase, ≤60 characters — detail belongs in Technical Reference or Session Log
- Never delete completed tasks — mark [x]
- Promote significant decisions to Decisions Log in Project Overview.md
- Keep Technical Reference.md current as decisions are made
- Keep all files lean — capture what matters, avoid noise

# CLAUDE.md

This file was generated from a reusable project template. The structure below is standard across all projects using this framework. You are working in a specific project instance, not the template itself.

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
Check `1. Project Management/Audits/` for any files with `Status: Open` or `Status: In Progress`. Treat open findings as active work items alongside the WP backlog. Do not rely on a hardcoded list here — read the directory to find current audit state.

## Work Package Conventions
- Create a new WP when work has a distinct milestone, sprint, or audit to close. Add to the existing backlog WP (e.g. WP3.1 or equivalent) for standalone improvements with no natural grouping.
- If the project has multiple components (web + mobile, frontend + backend), prefix WP tasks with the component (e.g. `[Web]`, `[iOS]`) and add a subsection per component in Technical Reference.

## Session Log Format
Each entry should include, at minimum:
- **Status** — `STARTED` or `COMPLETED`
- **What Was Done** — grouped by feature area
- **Decisions Made** — non-obvious choices worth preserving
- **Pending / Next Session** — open items handed off

Flag any `STARTED` entry found at session start — it means a prior session was interrupted.

## Session Start Routine
1. Read `3. Work Packages.md`, `5. Session Log.md`, and any open audit files to establish current state
2. Flag any `STARTED` entry in the Session Log immediately
3. Confirm next priorities before beginning work

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

## Memory vs PM Files
The Claude memory system (`~/.claude/projects/.../memory/`) is for thin cross-session pointers only — not content. All durable knowledge lives in PM files (committed to the repo):
- Architecture decisions → Decisions Log (`2. Project Overview.md`)
- Conventions, patterns, gotchas → `4. Technical Reference.md`
- Memory files should point to Technical Reference sections, not duplicate content

## PM Improvement Suggestions
If you observe a gap or friction point in this PM structure, log it in:
`1. Project Management/6. PM Template Improvement Suggestions.md`

This includes suggested changes to CLAUDE.md itself — since this file is template-sourced and should not be edited directly in a project instance, log any proposed CLAUDE.md improvements there so they can be evaluated and promoted to the template.

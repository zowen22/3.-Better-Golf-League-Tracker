# Handoff: [Short Task Title]

*Status: `Open` / `In Progress` / `Done` / `Blocked`*
*Created: [date] — Planner: [model/session]*
*Priority: `High` / `Medium` / `Low` — Effort: `S` / `M` / `L`*
*Depends on: [other handoff files that must land first, or `None`]*
*Parallel-safe: `Yes` / `No` — safe to run alongside other Open handoffs if their Critical Files don't overlap*

-----

> One independently-executable unit of work per document. Related findings from
> the same audit get separate handoffs unless one directly depends on another.
> The executor reads this cold — no shared context, no memory of the planning
> session. Everything needed to act correctly must be in this document.

## Goal

*The outcome, not the steps. Lets the executor sanity-check mid-task: "does what I'm doing still serve this?"*

## Context

*Briefing for someone who wasn't in the room. Why this work exists, what discussions led here, what the user cares about.*

## Findings / Evidence

*What was observed, where, and why it matters. Use `file:line` references, severity, and reasoning — the executor should be able to verify each finding before acting on it.*

## Scope

### In

### Out

*The highest-leverage section for preventing scope creep. A fresh session will be tempted to "fix" adjacent issues — list what was seen and deliberately left alone.*

## Implementation Plan

*Ordered, concrete steps referencing existing code and patterns. Not pseudocode-level, but unambiguous about approach and order.*

1. 

## Stop Conditions

*The most important section. Anywhere the planner would use judgment mid-task — an ambiguous requirement, a decision needing user input, evidence contradicting the findings — becomes an explicit, checkable condition here. If planning left a decision unresolved, that indecision belongs here too. On hitting one: stop, mark Status `Blocked`, note it in the Execution Report, and ask the user.*

- 

## Definition of Done

*Checkable, and where possible runnable. Include the actual commands (test suite, lint, smoke check) — a cold session doesn't know this project's verification habits.*

- [ ] 
- [ ] Verification commands pass: `[command]`
- [ ] Execution Report below is filled in
- [ ] Status updated to `Done`

## Critical Files

*Every file this handoff touches. Used both to execute and to judge parallel-safety against other Open handoffs.*

| File | Why |
|------|-----|
|      |     |

-----

## Execution Report

*Filled in by the executor. This closes the loop — the user or a later planner session reviews the work from here, not from diff archaeology.*

*Executed: [date] — Executor: [model/session]*

### What Was Done

- 

### Deviations from Plan

*Anything done differently than the Implementation Plan specified, and why.*

- 

### Follow-ups Discovered

*Out-of-scope issues noticed during execution. Log here; do not fix.*

- 

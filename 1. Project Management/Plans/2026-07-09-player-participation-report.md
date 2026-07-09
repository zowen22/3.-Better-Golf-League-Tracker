# Plan: Player Participation / Attendance Report

*Status: `Evaluating`*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, item #11)*

-----

## GLT page covered

`individual/player-participation` — season attendance summary per player: Rounds Scheduled, Rounds Played, Participation %, Sub Count, Absent Count.

## Current BGLT state

Absences are already tracked in the `player_absences` table (used by the Weekly Recap's Absences & Subs section, and by the sub-request workflow) — the raw data this report needs already exists. What's missing is a **rolled-up season summary report** aggregating it per player: nothing currently answers "who has missed the most rounds this season" or "what's Player X's participation rate" at a glance.

This is one of the more clearly valuable, low-ambiguity gaps found this pass — commissioners plausibly want this for planning subs and gauging roster reliability.

## Decision

No real two-approach split here either — this is a straightforward aggregation report:

1. Per season, per player: count scheduled matchups (excluding byes), count actually-played rounds (scorecard exists, not absent), count rounds with a sub, count rounds absent (no sub), compute participation % = played / scheduled.
2. Likely lives under Stats & Records or as a new admin-facing report (commissioners are the primary audience for this one, more than players).

*Effort:* S — pure aggregation over existing tables (`matchups`, `scorecards`, `player_absences`), no new schema needed.

## Open questions for @user

- Admin-only view, or visible to all members? (Attendance data could be seen as sensitive/social — worth a deliberate call rather than defaulting to public.)

## Next step

Cheap to build once the visibility question is answered — good candidate for an early pick from this batch of plans given low effort + clear value.

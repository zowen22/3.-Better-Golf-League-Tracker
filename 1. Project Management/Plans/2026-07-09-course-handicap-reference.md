# Plan: Course Handicap Reference Sheet + Filtered Lookup Matrix

*Status: `Evaluating`*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #16, #17)*

-----

## GLT pages covered

1. `league/course-handicap-player-list` — full roster reference sheet: each player's computed course handicap at every course/tee combination in the system (front/back/total rating, slope, par).
2. `league/course-handicap-player-matrix` — the same course-handicap lookup, filtered down to one Course/Tee/Gender/Side at a time.

## Current BGLT state

`handicap.py` tracks handicap **per round actually played** (`handicap_history`, `handicap_at_time_of_play`) — there's no precomputed reference table showing "if Player X played at Course Y on Tee Z, their course handicap would be N" for every course/tee combination in the system, independent of whether they've ever actually played there. This is a genuinely different capability: a lookup/reference tool rather than a history log.

## Decision — is this worth building given BGLT's course catalog is admin-curated (not every course a player might play)?

**Approach A: Build the full reference sheet**, computing course handicap = `round(handicap_index * slope / 113 + (rating - par))` for every active player × every course/tee combination currently in BGLT's course catalog.
- *Tradeoffs:* real value for pre-round tee-sheet planning ("what strokes does everyone get today") — this is genuinely how course handicaps are used in practice, GLT clearly thought this mattered enough for two separate pages. Requires the formula to already be correct and consistent with what `handicap_at_time_of_play` computes today (verify, don't reimplement differently).
- *Effort:* S–M — mostly a query/table, not new domain logic if the course-handicap formula is already implemented elsewhere in the codebase.

**Approach B: Skip the standalone reference sheet; rely on the existing per-round computation** (each scorecard already shows the player's course handicap for that specific round/tee at entry time).
- *Tradeoffs:* cheaper (nothing to build), but loses the "look up in advance" use case — a player or admin can't check "what would my course handicap be at Course X" without actually creating a round first.

**Recommendation: lean A** if pre-round planning/reference is something commissioners or players actually ask for; otherwise B (do nothing) is defensible since the existing scorecard-time computation already covers the moment it matters most.

## Open questions for @user

- Is this a real pain point — do players/commissioners want to look up "what's my handicap at Course X" before a round is scheduled there? Or does the existing tee-sheet/scorecard-time computation already cover the need?

## Next step

Low-effort if approved (mostly a display layer over an existing formula) — confirm real demand with @user before building, since it's plausible the existing per-round computation already satisfies the actual use case.

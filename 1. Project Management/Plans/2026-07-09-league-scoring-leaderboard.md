# Plan: League-Wide Scoring-Average Leaderboard

*Status: `Decision: build as a standalone page` — @user 2026-07-10. Technical spec: `Plans/2026-07-10-leaderboard-and-comparison-technical-spec.md`.*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, item #20)*

-----

## GLT page covered

`league/league-scoring-average` — a ranked leaderboard of **every player in the league**, ordered by scoring average, with hole-by-hole averages shown per player (Pos, Player, Course, Rounds, hole-by-hole 1-9, Gross Out, Net Out, presumably back-9 + total too).

## Current BGLT state

`stats.py`'s hole-averages page (`/hole-averages`) computes per-hole scoring averages either for **one selected player** or **league-wide difficulty** (all players combined, i.e. "how hard is this hole" rather than "how does each player rank") — it does not currently rank all players against each other by their own scoring average.

This is a real but narrow gap: the underlying per-player, per-hole average calculation almost certainly already exists (it's needed for the single-player view) — what's missing is running that same calculation for every player at once and sorting the result into a leaderboard.

## Decision

This doesn't have a meaningful two-approach split — it's a small, mostly-mechanical extension:

1. Reuse the existing per-player hole-average query, but loop it (or rewrite as one query grouped by player) across the whole active roster instead of one selected player.
2. Rank by an aggregate (season scoring average) with hole-by-hole shown as supporting detail, matching GLT's layout.

*Effort:* S — smallest of the gaps identified this pass, since the hard part (the averaging logic) already exists.

## Open questions for @user

- ~~Should this live as a new tab/mode on the existing `/hole-averages` page, or a separate "Scoring Leaderboard" page?~~ **Answered 2026-07-10 — standalone page.**

## Next step

Spec'd — see `Plans/2026-07-10-leaderboard-and-comparison-technical-spec.md`.

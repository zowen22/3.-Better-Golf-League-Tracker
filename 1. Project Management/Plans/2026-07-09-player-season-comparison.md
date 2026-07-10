# Plan: Player-Level Season-Over-Season Comparison

*Status: `Decision: compare gross average, net average, and handicap average` — @user 2026-07-10. Technical spec: `Plans/2026-07-10-leaderboard-and-comparison-technical-spec.md`.*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, item #25)*

-----

## GLT page covered

`league/season-comparison` — per-player comparison between two selected seasons: a chosen stat's Value in Season 1 vs. Season 2, Amount Change, % Change — plus a handicap before/after comparison.

## Current BGLT state

`stats.py`'s `/compare` page already does season-over-season comparison, but at the **team** level (avg gross, low gross, points leader, standings leader, etc. per season) — there's no player-level equivalent letting someone pick "Player X, Season A vs Season B" and see the delta.

## Decision

Small, mostly-mechanical extension similar in shape to the League Scoring Leaderboard plan (`2026-07-09-league-scoring-leaderboard.md`) — no real two-path ambiguity:

1. New page (or new mode on `/compare`): pick a player + two seasons, show the same kind of per-season stat set already computed elsewhere in the player profile (rounds, avg gross, points, W-T-L, handicap) side by side with a delta column.
2. Handicap before/after is already tracked in `handicap_history` — just needs picking the right two data points (season start vs. season end, or first vs. last recorded).

*Effort:* S–M — depends on how many stats @user wants in the comparison; the season-scoped versions of each stat likely already exist individually in the player profile and just need pulling side by side.

## Open questions for @user

- ~~Which stats matter most for this comparison?~~ **Answered 2026-07-10 — gross average, net average, and handicap average.** Points/W-T-L not included.

## Next step

Spec'd — see `Plans/2026-07-10-leaderboard-and-comparison-technical-spec.md`.

# Plan: Best-Ball Format — Clarifying Question (not yet a build plan)

*Status: `Evaluating`*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #22, #26, #35)*

-----

## GLT pages covered

1. `league/player-best-ball` — "Player Best Ball - Season": individual best-ball format leaderboard (best score among a group, per hole, aggregated for the season).
2. `league/team-best-ball` — same format, team-level.
3. `standings/team-bestball-stroke-results` — best-ball format team stroke results within standings.

## Why this is a question, not a plan yet

BGLT's `scoring_mode` setting supports exactly two formats: `match_play` and `stableford`. There is **no best-ball scoring format anywhere in the codebase** — not a partial implementation, not a dead setting, nothing. Three of GLT's ~36 stat pages exist purely to report on a scoring format BGLT has never had any notion of.

Before scoping anything here, the real question is whether this league (or leagues BGLT might serve in the future) actually plays best-ball at all. If not, these three GLT pages are simply not applicable — GLT supports more scoring formats than BGLT does by design, and that's fine; it doesn't need to be "gap-filled" just because GLT has it.

## Open question for @user

**Does this league play best-ball (or would a future BGLT league)? If not, these three pages can be marked "not applicable" and closed out — no build needed.**

## Next step

Do not schedule any build work here until @user answers the question above. If the answer is "yes, we want best-ball," this becomes a genuinely large plan (new scoring_mode value, new scoring calculation engine, new standings/leaderboard pages) — worth its own dedicated planning pass at that point, not a quick add.

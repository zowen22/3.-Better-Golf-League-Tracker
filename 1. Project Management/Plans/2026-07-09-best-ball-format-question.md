# Plan: Missing Scoring Formats (Best Ball, Team Totals, High/Low, Stroke Play) — Clarifying Question

*Status: `Evaluating`*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #22, #26, #35)*
*Updated: 2026-07-09 — @user found GLT's own `/glthome/about/features` marketing page, which lists every supported scoring format explicitly. This upgrades the framing below from "is this even a real GLT feature" (unconfirmed, inferred from stat-page names alone) to "these are GLT's actual documented scoring options — the only open question is whether @user's league wants them."*

-----

## GLT pages originally covered

1. `league/player-best-ball` — "Player Best Ball - Season": individual best-ball leaderboard (best score among a group, per hole, aggregated for the season).
2. `league/team-best-ball` — same format, team-level.
3. `standings/team-bestball-stroke-results` — best-ball format team stroke results within standings.

## Prior context worth noting

The Settings Parity audit (`7. GLT Feature Parity.md` Part 1, "Point Rules & Scoring Formats," 2026-07-04) had *already* identified Stroke Play/Best Ball/Team Totals/Low Net as GLT settings-list categories with zero BGLT equivalent, based on the raw settings list alone, and already concluded "adding [these] would be a genuinely large structural feature (a second scoring engine, not a settings tweak)." The `/features` page below doesn't overturn that — it independently corroborates it from GLT's own marketing copy and adds one new detail (composability) that the settings-list audit didn't surface.

## What `/glthome/about/features` confirms (new this update)

GLT's own "Scoring Options" section lists exactly these formats, verbatim:

> - **Match Play Scoring**: Points per hole, points per match, and points per team match. The match points can be determined by total net score, or by total points of the holes.
> - **Stableford Scoring**: Customizable points for each hole, points per match, and points per team match. The match points can be determined by total net score, or by total stableford score.
> - **Best ball** (low score of the teammates)
> - **Team totals** - Add together the scores from each team member
> - **High/low of each teammate**
> - **Stroke Play** - Award points based on position finished in the round for both net and gross totals. For team play, both player's points are added together for a team total.
> - *"You can combine any of the scoring options for your league"*

So GLT actually ships **6 scoring formats**, not the 2 this plan doc originally focused on, and they're **composable** (a league isn't locked into exactly one). Cross-referenced against BGLT's `scoring_mode` setting (`app/routes/admin.py`, `app/routes/api.py`, etc.): BGLT supports **`match_play` and `stableford` only** — confirmed still accurate, and confirmed those two are implemented consistently with GLT's own definitions (points per hole/match/team-match, determined by net score or points/stableford score). The other **four formats have zero implementation in BGLT**:

| Format | GLT description | BGLT status |
|---|---|---|
| Best ball | Low score of the teammates counts for the team/hole | 🔴 Not implemented |
| Team totals | Both teammates' scores added together | 🔴 Not implemented |
| High/low of each teammate | One teammate's high score + the other's low score combined (a distinct rule from best-ball, not a duplicate) | 🔴 Not implemented |
| Stroke Play | Points awarded by finishing position in the round, both net and gross | 🔴 Not implemented |
| *(combining formats)* | A league can mix formats | 🔴 Not implemented — `scoring_mode` is a single enum value, not composable |

## Decision — still not a build plan yet, but the shape of the question changed

This is no longer "does this obscure-sounding feature even apply here" — GLT actively markets all 6 as core, equal-weight scoring options. The real question is now a straightforward product one: **does @user's actual league play (or want to offer) any format beyond match play/stableford?** If yes, this becomes real, substantial work — a new `scoring_mode` architecture (probably moving from a single enum to a composable set, given GLT explicitly supports combining formats), a real scoring-calculation engine per format, and the associated leaderboard/report pages (#22, #26, #35 above, plus whatever new reports a new format would need).

## Open question for @user

**Does this league (or would a future BGLT league) actually want any of Best Ball, Team Totals, High/Low, or Stroke Play — either standalone or combined with the existing Match Play/Stableford support? If the answer is "match play and stableford cover everything we need," these four formats and their associated stat pages can be closed out as intentionally-not-supported, not a gap to fill.**

## Next step

Still blocked on the question above before any scoping work. If any format is wanted, recommend treating it as its own dedicated planning pass given the likely need to redesign `scoring_mode` from a single value into something composable (per GLT's "combine any of the scoring options" capability) rather than bolting one more `elif` onto the existing enum.

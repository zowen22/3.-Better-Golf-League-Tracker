# Plan: Additional Scoring Formats (Best Ball, Team Totals, High/Low, Stroke Play)

*Status: `Decision: build all 4 as fixed presets, no composability` — @user approved 2026-07-09: "We want the additional scoring formats - but we don't need to be able to do multiple formats at the same time. Really, I'm imagining the scoring formats essentially as presets for the wealth of scoring options available." — architecture below still needs sign-off before implementation starts (see Open Questions).*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #22, #26, #35)*

-----

## GLT pages originally covered

1. `league/player-best-ball` — "Player Best Ball - Season": individual best-ball leaderboard (best score among a group, per hole, aggregated for the season).
2. `league/team-best-ball` — same format, team-level.
3. `standings/team-bestball-stroke-results` — best-ball format team stroke results within standings.

## Prior context

The Settings Parity audit (`7. GLT Feature Parity.md` Part 1, "Point Rules & Scoring Formats," 2026-07-04) had already identified Stroke Play/Best Ball/Team Totals/Low Net as GLT settings categories with zero BGLT equivalent. `/glthome/about/features` (GLT's marketing page, found by @user) independently corroborated this and confirmed exactly what each format means:

> - **Best ball** (low score of the teammates)
> - **Team totals** - Add together the scores from each team member
> - **High/low of each teammate**
> - **Stroke Play** - Award points based on position finished in the round for both net and gross totals. For team play, both player's points are added together for a team total.
> - *"You can combine any of the scoring options for your league"*

@user's decision: build all 4 — but explicitly **does not** want GLT's composability ("combine any of the scoring options"). @user's framing: think of each scoring format as a **preset** over BGLT's existing wealth of scoring options, not a fully general combinable matrix. A league picks exactly one format; no per-week or per-flight mixing.

## Why this needs an architecture decision before building

BGLT's current scoring engine (`scores.py`) is more structurally rigid than the settings audit alone made obvious. `_recalc_matchup_scoring()`'s `match_result()` always does this, unconditionally:

1. Split each 2-player team into an A/B pairing, sorted by playing handicap (`team_ab()`).
2. Compute **individual head-to-head**: A-vs-A and B-vs-B, hole-by-hole, using either `calc_match_play()` (net-score comparison) or `calc_stableford()` (stableford-point comparison) depending on `scoring_mode`.
3. There is currently no code path anywhere that combines **two teammates' scores into one team score** before comparison — every hole/match result today is fundamentally player-vs-player, never team-vs-team.

That's the real gap. Best Ball, Team Totals, and High/Low all require a genuinely new step: "combine this team's two players' scores on this hole into a single number" (min of the two / sum of the two / high-of-one-plus-low-of-other, respectively) — which then gets compared to the opposing team's combined number, using the *same* point-awarding logic (`calc_match_play` or `calc_stableford`) that already exists. Stroke Play is a third, different kind of change again: it's not a head-to-head team match at all — it's a **field-wide ranking** (every player/team ranked by total score across the whole group, points awarded by finish position), which doesn't fit the existing matchup-pair model at all.

## Proposed architecture (for @user sign-off before implementation)

Given @user's "presets" framing, and matching how GLT's own settings list is actually structured (separate `Best Ball Points`, `Team Totals Points`, `Stroke Play Points` categories, each with their own settings — not one shared combinable engine), the recommended shape is:

1. **Extend `scoring_mode` from a 2-value to a 6-value enum**: `match_play`, `stableford`, `best_ball`, `team_totals`, `high_low`, `stroke_play`. One value per league, no combining — matches @user's explicit "not at the same time" requirement.
2. **Best Ball / Team Totals / High-Low** slot into the *existing* head-to-head matchup framework with one new step inserted before scoring: compute each team's per-hole "team score" (min / sum / high+low of the two teammates), then feed that into the *same* `calc_match_play()`/`calc_stableford()` logic already used today — reusing, not duplicating, the point-award math. This is the cheapest of the four to build precisely because it reuses so much.
3. **Stroke Play** is the outlier — it needs its own ranking/points computation (field-wide position, not team-vs-team), and likely its own standings view, since it doesn't produce a `match_results` row per the current matchup-pair shape at all.
4. Settings UI: one new settings sub-section per format, mirroring GLT's own category split (own point-value tables per format) rather than trying to retrofit new formats into the existing Match Play/Stableford settings sections.

## Open questions for @user (before implementation starts)

1. **Point-awarding for the 3 team-score formats**: does each of Best Ball / Team Totals / High-Low get its *own* dedicated point-value settings (matching GLT's literal settings categories — "Best Ball Points," "Team Totals Points" as distinct 12/6-setting groups), or should they reuse whichever of Match Play/Stableford's point values are already configured? (Recommend: own dedicated settings, matching GLT's actual structure — but confirm before building, since it's more settings-UI surface either way.)
2. **Stroke Play scope**: does this league want Stroke Play as a genuine field-wide ranking (points by finish position across everyone, not team-based), matching GLT's description exactly? This is architecturally the largest single piece of the four — confirm it's actually wanted before scoping it in detail, since Best Ball/Team Totals/High-Low could ship as a smaller first phase without it.
3. **Rollout scope**: build all 4 in one pass, or ship Best Ball/Team Totals/High-Low first (cheaper, shares the existing matchup framework) and treat Stroke Play as a separate follow-on given its larger structural difference?

## Next step

Architecture proposed above — need @user's sign-off on the 3 open questions before writing any scoring-engine code, given this changes core logic that runs every week for every league using BGLT. Recommend treating this as its own dedicated build (likely multi-session), separate from the smaller Stats-page gaps in the other 8 plan docs from this pass.

# Plan: Additional Scoring Formats (Best Ball, Team Totals, High/Low, Classical Stroke Play)

*Status: `Decision: build 4 new presets over a shared GLT-matched settings surface; GLT's field-position stroke play stays a setting, not a preset` — finalized 2026-07-09 across several rounds of clarification with @user (see history below). Still needs a full technical spec before implementation (see Next Step).*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #22, #26, #35)*

-----

## GLT pages originally covered

1. `league/player-best-ball` — "Player Best Ball - Season": individual best-ball leaderboard (best score among a group, per hole, aggregated for the season).
2. `league/team-best-ball` — same format, team-level.
3. `standings/team-bestball-stroke-results` — best-ball format team stroke results within standings.

## How this decision was reached (condensed history)

1. Settings Parity audit (Part 1, 2026-07-04) first identified Stroke Play/Best Ball/Team Totals/Low Net as GLT settings categories with no BGLT equivalent, already concluding they'd need "a second scoring engine, not a settings tweak."
2. `/glthome/about/features` (GLT's marketing page, found by @user 2026-07-09) independently corroborated this and defined each format in plain English, plus revealed GLT allows combining formats.
3. @user decided: **want all 4 additional formats, but explicitly do not want GLT's composability** — one format per league, framed as "presets... for the wealth of scoring options available."
4. Clarifying round on architecture surfaced two real design questions (dedicated vs. shared settings per format; whether to include Stroke Play in this build). @user's answers, given via voice-to-text over a couple of messages:
   - **Settings surface**: build one comprehensive settings library **matching GLT's actual settings-list categories** (Match Play Points, Stableford Points, Best Ball Points, Team Totals Points, Stroke Play Points–Individual/–Team/–vs the Field, General Point Rules, Low Net — all real categories already enumerated in Part 1's settings audit). A **preset** is a curated bundle/interpretation over that one shared surface — picking "Best Ball" makes the Best Ball Points settings the ones that govern scoring — not a reduction to fewer total settings, and not literal number-sharing between formats (e.g. Best Ball doesn't borrow Match Play's specific point values).
   - **Stroke Play is two different things, only one becomes a preset**: GLT's actual "Stroke Play" (points by finishing position in the field, "vs the Field") is a non-classical, GLT-specific variant — @user wants this to exist only as an available **setting** within the plethora (matching GLT's "Stroke Play Points - vs the Field" category), *not* elevated to a named top-level preset. What *does* become a preset is **"Classical Stroke Play"**: score relative to par, translated directly into points (over-par rounds cost points, better-than-par rounds earn them) — not a rank/position system, not Stableford's tiered curve.
   - **Exact point values deferred**: @user explicitly said the sign convention and specific numbers for the Classical Stroke Play preset can be figured out later, as long as the settings scaffolding matches GLT's list now. Do not guess/hardcode these values — they're an open follow-up, not part of this plan's scope.

## Final scoring-format lineup

| Preset (top-level, one per league, no combining) | Mechanic |
|---|---|
| Match Play *(existing)* | Individual A-vs-A/B-vs-B, net-score comparison, points per hole/match/team-match |
| Stableford *(existing)* | Same individual structure, stableford-point comparison |
| Best Ball *(new)* | Team score per hole = min(teammate A, teammate B); compared using the existing point-award logic |
| Team Totals *(new)* | Team score per hole = teammate A + teammate B; same point-award logic |
| High/Low *(new)* | Team score per hole = one teammate's high + the other's low; same point-award logic |
| Classical Stroke Play *(new)* | Field-wide, not team-vs-team: total score relative to par converted directly to points. Exact point curve/sign TBD later. |

GLT's rank/position-based "Stroke Play vs the Field" is **not** in this table — it remains an available setting (matching GLT's own "Stroke Play Points - vs the Field" category) for later, not a preset.

## Why this needs a real architecture (not just a settings toggle)

BGLT's current scoring engine (`scores.py`) is more structurally rigid than the settings audit alone made obvious. `_recalc_matchup_scoring()`'s `match_result()` always does this, unconditionally: split each 2-player team into an A/B pairing by handicap, then compute **individual head-to-head** (A-vs-A, B-vs-B) hole-by-hole via `calc_match_play()` or `calc_stableford()`. There is currently no code path that combines two teammates' scores into one team score before comparison — every result today is player-vs-player, never team-vs-team.

Best Ball / Team Totals / High-Low all need one new step inserted before scoring: compute each team's per-hole "team score" (min / sum / high+low), then feed that into the *same* `calc_match_play()`/`calc_stableford()` point-award logic already in use — reusing the point engine, not duplicating it. Classical Stroke Play is architecturally different again: field-wide ranking, not a team matchup at all, so it doesn't produce a `match_results` row shaped like today's and likely needs its own standings view.

## Next step

**Technical spec written 2026-07-10**: `Plans/2026-07-10-scoring-formats-technical-spec.md` — schema, the consolidated scoring-engine refactor, the team-score-combination layer, and a phased rollout plan. One genuine open question surfaced during spec work: GLT's "High/Low of each teammate" is ambiguous enough (two real, different golf formats go by similar names) that it needs @user confirmation before it's built — see that doc's Open Questions section.

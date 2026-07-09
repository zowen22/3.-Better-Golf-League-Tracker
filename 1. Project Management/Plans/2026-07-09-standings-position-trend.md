# Plan: Standings Position (Rank) Trend, Alongside Points Trend

*Status: `Evaluating`*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, item #34)*

-----

## GLT page covered

`standings/standings-race` — "League Standings Position": a chart tracking each team's standings **position/rank** over the course of the season (chart-library markers confirmed present in the raw HTML; exact chart type not confirmed from HTML alone — flagged in the Feature Parity doc as needing @user's visual read too).

## Current BGLT state

`standings.py`'s `/trend` route already charts cumulative **points** per team, per week, as a line chart. Points and rank are related but not identical: a team can gain points every week and still *drop* in rank if other teams are gaining faster — so a points-trend chart and a position-trend chart can tell meaningfully different stories, especially in a tight standings race late in a season.

## Decision — is a separate rank-over-time chart worth adding alongside the existing points chart?

**Approach A: Add rank as a second chart (or a toggle) on the existing `/trend` page** — same weekly data already being computed for the points trend, just also compute and chart `rank` at each week's snapshot instead of (or in addition to) raw points.
- *Tradeoffs:* small addition once the existing trend infrastructure is in place — the points-by-week data is already being assembled, rank is just a sort of that same data at each week.
- *Effort:* S.

**Approach B: Leave points-only** — argue that points trend is more informative anyway since it shows margin, not just ordinal position (rank alone hides how close a race actually is).
- *Tradeoffs:* cheaper (nothing to build), but doesn't match what GLT chose to ship, and "who's actually in Nth place each week" is a genuinely different, simpler question than "how many points does each team have."

**Recommendation: lean A** — cheap to add given the trend infrastructure already exists, and rank is a more immediately readable stat for casual league-standing-watchers than raw point totals.

## Open questions for @user

- Confirm what GLT's chart is actually showing (I can't fully verify chart type/exact metric from raw HTML alone) — is it truly rank position over time, or something else entirely?
- If rank: worth adding as a toggle on the existing trend page, or a fully separate page?

## Next step

Cheap if approved — likely the second-cheapest item in this batch of plans after the League Scoring Leaderboard, since it reuses existing weekly-points infrastructure.

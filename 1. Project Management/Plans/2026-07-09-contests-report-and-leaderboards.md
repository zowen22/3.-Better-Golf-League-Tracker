# Plan: Unified Contest Winners Report + Season Leaderboards

*Status: `Evaluating` — scope question resolved 2026-07-10: @user wants **both** season-scoped and all-time views (see updated Open Questions).*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #1, #2, #3, #4)*

-----

## GLT pages covered

1. `contests/contest-winners` — flat, filterable (Contest type / Round / Player / Team) log of every contest winner across the whole season: Contest Name, Week #, Date, Course, Winner, Hole #, Distance, Amount Won, Comments.
2. `contests/contest-winners-summary` — per-player total $ won across all contests, filterable by Contest type/Segment.
3. `contests/individual-low-score` — season-long log: one row per week showing that week's Low Net and Low Gross winner.
4. `contests/individual-skins-leader` — season skins leaderboard: Pos, Name, #Skins, $Won, Owed/Paid, Net.

## Current BGLT state

The Contests redesign shipped 2026-07-09 built a per-contest results table with a near-identical column set (Week #, Date, Course, Contest Winner, Result, Hole #, Distance, Amount Won, Comments) — but it's deliberately scoped to **one contest at a time** (`admin_edit.html`), not a unified cross-contest view. That scope call was flagged explicitly at the time as a possible follow-up. Skins (`skins.py`) shows per-round winners and a season overview, but no ranked per-player leaderboard summing skins won across the season. Weekly Recap computes low gross/net for one week on the fly; nothing persists a season-spanning "who won low score each week" log.

## Decision — build one unified report page, or extend the existing per-contest view?

**Approach A: New standalone "Contest Winners" report page** (mirrors GLT's actual page), with the same 4 filter dropdowns (Contest type, Week, Player, Team), aggregating results across every contest in the season into one flat table.
- *Tradeoffs:* matches GLT's UX exactly; requires a new route + query joining `contests` + `contest_results` without a single-contest scope. Reasonably small — the per-result data already has everything needed (added this session: `week_num`, `distance`, `amount_won`).
- *Effort:* S–M.

**Approach B: Add cross-contest filters to the existing per-contest page** by turning "contest_id" into just another optional filter instead of a hard route parameter.
- *Tradeoffs:* less new surface area, but conceptually muddies a page that's currently "edit this one contest" — the admin-facing page and a read-only leaderboard page probably shouldn't be the same view.
- *Effort:* S, but likely needs rework later once a genuine read-only leaderboard is wanted anyway.

**Recommendation: A.** A dedicated read-only report (likely member-facing, under Stats) is cleaner than overloading the admin edit page, and matches what GLT actually ships.

## Scope if approved

1. New report page: flat table across all contests for the season, Contest/Week/Player/Team filters.
2. Per-player "$ won across contests" summary (small, derived from the same query — just grouped differently).
3. Season-long "Low Score winners by week" log — could reuse the Weekly Recap's low-gross/low-net calculation logic rather than reinventing it, persisting a snapshot per week instead of only computing on-demand for one email.
4. Season skins leaderboard — ranked, aggregating `skins.py`'s existing per-round winner data by player.

## Open questions for @user

- ~~Should this report span one season or all-time across seasons?~~ **Answered 2026-07-10 — both.** The report needs a season filter that includes an "All-time" option, not just a fixed single-season scope. This applies to the unified contest-winners table (#1) and likely the $-won summary (#2) and skins leaderboard (#4) too, for consistency — the season low-score log (#3) is inherently week-by-week within a season already, so "all-time" there just means "don't reset the log each season," i.e. keep it queryable across seasons the same way.
- Where should it live in the nav — Contests page itself (a new "All Results" tab) or under Stats & Records?

## Next step

Nav placement is the only remaining open question — architecture is otherwise ready to build: a season filter (with an "All-time" option spanning every season) on the unified report, the $-won summary, and the skins leaderboard, no further scope decisions expected before implementation.

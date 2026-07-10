# GLT Field-Position Stroke Play — Technical Spec

**Status:** Decision: Declined (2026-07-10, @user: "Go ahead" on this spec's recommendation)
**Type:** Technical Spec
**Linked WP:** GLT Feature Parity #30/#31, open since the 2026-07-09 assessment; explicitly deferred again during the 2026-07-10 scoring-formats build ("kept as a possible future setting, not a preset, per the decision"). Closed 2026-07-10 — no signal of real demand across 3 review passes; revisit only if it resurfaces with a concrete want.
**Prepared by:** Claude, 2026-07-10

## Context

The GLT parity doc has carried #30 (`individual-season-stroke-play-results`) and #31 (`individual-stroke-play-results`) as open since the original assessment, each time deferred with "not built, not asked about since." This spec exists to finally pin down **what these actually are**, since "Stroke Play" is used by GLT for two structurally different things in this project's own docs, and that ambiguity is why the item keeps getting punted instead of decided.

## The naming collision, resolved

**BGLT's Classical Stroke Play** (built 2026-07-10, Phase 3 of the scoring-formats spec) converts each week's par-relative net score directly into points (`(par − net) × points_per_stroke`), summed across **every** week, feeding the exact same points-based team-standings system every other format uses. It's field-wide (not pairwise) in how points are *earned*, but the season standings around it are unchanged.

**GLT's field-position Stroke Play** (#30's actual description: "Stroke-play-format standings (best-N-of-M rounds)") is a different thing entirely: a **score-based ranking that only counts a player's best N rounds out of M played that season** — like a tour money-list cut ("best 8 of 12 events count"), with players ranked by cumulative score across just that subset, **not by points at all**. #31 ("Stroke-play leaderboard with hole detail, filterable by round/group") is a display layer on top of #30's ranking — a leaderboard with drill-down, not a separate computation.

These are not the same feature wearing different names — one is a points-conversion scoring *format* (built), the other is an entirely separate best-N-of-M score-based *standings system* that doesn't touch the points engine at all (not built, not started).

## What building #30/#31 for real would require

BGLT's whole standings architecture is `SUM(match_results.total_points) GROUP BY team_id/player_id` — every format, including Classical Stroke Play, works by producing points that feed this one aggregation. A genuine best-N-of-M score-based ranking is **orthogonal to that system**, not an extension of it:

- A new per-player "eligible rounds pool" concept — which N of the player's M rounds count — conceptually similar to the handicap engine's existing drop-worst-N mechanism (`high_scores_to_drop`/`low_scores_to_drop` in `handicap.py`), but that machinery computes a **Handicap Index**, not a **standings rank**; reusing the pattern doesn't mean reusing the code, since the output feeds an entirely different page.
- A parallel ranking table/view, computed from raw scores (gross or net, TBD) rather than from `match_results` points at all — players who don't use this format wouldn't appear on it, and it would need to coexist with (not replace) the points-based standings a league is presumably still running for its actual match structure.
- The leaderboard/drill-down page (#31) would be straightforward once #30's ranking exists — it's a read layer on data that would already be computed, similar in shape to the already-built Scoring Leaderboard/Scoring by Year pages.

This is real, non-trivial scope — a new standings concept, not a settings wire-up or a display gap.

## Options

- **(a) Build it as a genuinely new standings mode.** Real feature work: define the eligible-rounds-pool rule (best N of M — N and M both need to be settings, mirroring the handicap engine's existing drop-count pattern), a new ranking query independent of `match_results`, and a new leaderboard page. Only worth doing if @user actually wants a tour-style "your best N rounds count" standings option separate from the points system every other format uses.
- **(b) Close it as Declined.** This item has been open across multiple parity passes with no real user interest expressed beyond "worth tracking" — if nothing about a best-N-of-M score-cut standings system resonates as something this league actually wants, it's reasonable to close it out now rather than let it keep rolling forward unresolved.
- **(c) Partial/cheaper middle path**: add a best-N-of-M *display filter* on top of the existing Classical Stroke Play points data (e.g., "show cumulative points using only your best N weeks") rather than a true parallel score-based ranking. This wouldn't match GLT's actual semantics (GLT's version ranks by raw score, not points) but might satisfy the underlying "don't let one bad week tank my season" instinct at a fraction of the cost, if that turns out to be the real motivation behind wanting this.

**Recommendation:** (b) unless @user specifically wants a genuine best-N-of-M score-cut standings mode — this has sat open with zero signal of real demand across three separate review passes (2026-07-09 assessment, 2026-07-10 scoring-formats build, now), and building (a) speculatively would be exactly the kind of premature feature work this project's conventions warn against. If there's a real want here, (c) is worth floating first as a much lower-cost way to test whether it actually addresses the underlying need before committing to (a)'s full parallel ranking system.

## Open Question for @user

Is there real interest in a best-N-of-M score-based standings mode (distinct from the points-based Classical Stroke Play already built), or should #30/#31 close as Declined? If there's interest, is it the full GLT-style score ranking (a), or would a simpler "best N weeks of your existing points" filter (c) actually cover the want?

## Critical Files (if (a) is chosen)

- `app/routes/handicap.py` (existing drop-worst-N pattern to reference, not reuse directly)
- `app/routes/standings.py` (existing points-based aggregation, to keep untouched/parallel)
- `app/routes/scores.py:253-` (`compute_classical_stroke_play_points()` — the points-based sibling this would sit alongside, not replace)

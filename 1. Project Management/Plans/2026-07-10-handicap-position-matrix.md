# Handicap Position (Rank) History Matrix — Technical Spec

**Status:** Evaluating
**Type:** Technical Spec
**Linked WP:** New idea from @user, 2026-07-10 — not a GLT parity item (no matching page found in `7. GLT Feature Parity.md`'s 36-page inventory), an original BGLT feature request.
**Prepared by:** Claude, 2026-07-10

## Context

@user asked for "a table that shows weeks at handicap position in the league... 1 through league qty of players with the y axis being names" — a matrix where each row is a player (y-axis) and each cell shows that player's **rank** (1st through Nth, N = number of ranked players) among the whole league for a given week, based on handicap.

This is a genuinely new idea, not a re-ask of anything already decided this session:
- **Not the same as the declined "Standings Race"** (parity #34, `Plans/2026-07-09-standings-position-trend.md`) — that was **team points rank** over time (a team's position in the standings), explicitly declined ("No don't need standings race"). This request is **individual handicap rank**, a completely different axis (skill/handicap position, not points position) that was never part of that decision.
- **Not the same as the existing Handicap Matrix** (`GET /handicap/league/<season_id>`, confirmed ✅ No Gap vs. GLT's `league-handicap-history`) — that page already shows the exact shape requested (rows = players, columns = weeks) but the **cell value is the raw playing handicap number**, not a rank/position. This request wants the same shape, ranked instead of raw.

The good news: the existing Handicap Matrix already computes and displays exactly the per-player, per-week handicap data this feature needs — nothing new to calculate, just a different way to display numbers that already exist.

## Design

### Data source — reuse, don't recompute

`handicap.league_matrix()` (`app/routes/handicap.py:991-`) already builds exactly the input this feature needs:
- One column per unique round date that season (`rounds`, built from `_date_map` collapsing multiple matchups on the same date into one column) — plus a "Current" column.
- `plays[pid][round_id]['hcp']` — each player's **playing handicap entering that round** (`scorecards.handicap_at_time_of_play`), already resolved per player per round.
- `player_rows` — every active player who's on a team or has played this season, already sorted `last_name, first_name`.

The new feature is a **ranking pass over the same per-column data**, not a new query: for each week/column, take every player's handicap cell that week, rank them ascending (lower handicap = better position = rank 1), and that rank is the new cell value — instead of the raw handicap number.

### Table shape (matches the request exactly)

- **Rows (y-axis):** player names — same sort order as the existing matrix (`last_name, first_name`), for visual consistency between the two views of the same underlying data.
- **Columns:** one per week/round-date (reusing the exact column set the existing matrix already builds), same sticky-header/scrollable-table pattern (`matrix-scroll`, sticky name column) already established in `league_matrix.html`.
- **Cell value:** that player's rank for that week — an integer from 1 to N, where N is however many players have a handicap value that week (not necessarily the full roster — see "no-play weeks" below).
- **Visual treatment:** reuse the medal-badge convention already used on `standings/individual.html` (🥇🥈🥉 for ranks 1-3) rather than inventing a new visual language — keeps the app consistent. A subtle background tint by rank tier (top third / middle / bottom third) would help scanning a wide table at a glance, similar in spirit to the matrix's existing `col-cell-override` highlight treatment.

### Handling edge cases

- **No-play weeks (bye, unsubbed absence):** a player with no handicap cell that week has no position that week — render blank/dash (`col-absent`, matching the existing matrix's exact treatment), don't rank them and don't leave a gap in other players' rank numbers (i.e., ranks are computed only among players who actually have a value that week, not padded to account for absent players).
- **Ties:** standard competition ranking (two players tied for the lowest handicap both show rank "1," the next player shows rank "3," not "2") — matches the convention `email_config._top_n_with_ties()` already established elsewhere in this codebase, for consistency. Flagged as an Open Question below in case dense ranking (1, 1, 2) is actually preferred for this specific view.
- **Provisional (pre-eligibility temp) handicaps:** the existing matrix already renders these in cells with no distinction from a "real" handicap — recommend the same for consistency, but flagged as an Open Question since ranking someone on a provisional number is a slightly different judgment call than just *displaying* one.

### Placement

Two ways to ship this, ranked by recommendation:

1. **(Recommended) A view-mode toggle on the existing Handicap Matrix page** ("Values" / "Position" tabs or a toggle button) — same route, same data already fetched, same table structure; only the cell-rendering logic branches. No new nav entry, no new page to maintain, and it puts the ranked view exactly where someone already looking at handicaps would think to find it.
2. **A separate new page/route** (e.g. `GET /handicap/league/<season_id>/position`) with its own nav entry — cleaner separation of concerns, but doubles the nav footprint for what's fundamentally the same dataset viewed two ways, and this session's nav restructure work was specifically about *not* letting the hamburger menu grow unnecessarily.

## Open Questions for @user

1. **Rank basis:** playing handicap (recommended — matches what the existing matrix already shows, reuses the data with zero new computation) or raw Handicap Index (the "purer" skill measure, unaffected by this league's %/cap settings, but would introduce a second definition of "handicap" not currently shown in matrix form anywhere)? These usually agree, but can diverge for subs (different temp-handicap %) or players near the `max_handicap_index` cap.
2. **Placement:** toggle on the existing Handicap Matrix page (recommended, smaller footprint) or a dedicated new page + nav entry?
3. **Row sort order:** alphabetical, matching the existing matrix (recommended, consistent with its sibling view) or sorted by current/latest rank (a "who's on top right now" framing, more leaderboard-like)?
4. **Provisional handicaps:** include them in that week's ranking (recommended, matches how the existing matrix already displays them with no distinction) or exclude/blank them until a player is fully eligible?
5. **Tie handling:** standard competition ranking — 1, 1, 3 (recommended, matches `_top_n_with_ties()` elsewhere in this codebase) or dense ranking — 1, 1, 2?

## Critical Files

- `app/routes/handicap.py:991-` (`league_matrix()` — the exact data source to reuse; a new ranking pass gets added here or in a sibling function depending on the placement decision)
- `app/templates/handicap/league_matrix.html` (existing table to extend with a toggle, or to model a new template after)
- `app/templates/standings/individual.html` (medal-badge rank-display convention to reuse for visual consistency)
- `app/routes/scores.py` (`calc_playing_handicap` — already used by `league_matrix()`, no changes needed, just confirming no new handicap computation is required)

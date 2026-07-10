# Plan: Player Scoring Detail Enhancements (Hole-by-Hole History, Opponent Stats, By-Course-by-Year, Net Categories)

*Status: `Decision: build #1 (Scoring History) and #4 (Scoring by Year) matching GLT's layout; #2/#3/#5/#6 declined` — @user 2026-07-10. Technical spec: `Plans/2026-07-10-scoring-history-and-by-year-technical-spec.md`.*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, items #7, #9, #10, #14, #15, #24)*
*Correction 2026-07-10: item #1's "Current BGLT state" below was wrong — a full hole-by-hole-per-round table already existed on the profile page (added well before the 2026-07-09 assessment). The real gap was only the missing Hdcp/Net/Pts/OUT-IN/Skins columns, not "no hole-by-hole detail at all." See the technical spec for the corrected scope.*

-----

## GLT pages covered

1. `individual/individual-scoring-detail` — full hole-by-hole gross score for **every round** a selected player has played, one consolidated table.
2. `individual/opponent-average` — per-player: own avg gross/hdcp/net vs. the **average of every opponent ever faced**, and the differential.
3. `individual/opponent-history` — chronological per-round log: my score/hdcp/net side-by-side with that round's specific opponent.
4. `individual/scoring-average-by-year` — per (Year × Course) for one player: rounds, front/back net averages, scoring-category counts.
5. `individual/scoring-history-summary` — round-level log (no hole detail): Date, Name, Course, Par, Rating, Slope, Score, Hdcp, Net, Pts, scoring-category counts.
6. `league/player-scoring-summary` — per-player Gross **and** Net eagle/birdie/par/bogey/double/other counts, side by side.

## Why these are bundled together

All six are variations on "give me more/richer detail about one player's scoring history" — they share the same underlying source data (`scorecards` + `hole_scores` + `matchups`, joined to the opponent's scorecard for the same round) and would likely be built as extensions to the existing `players.py` profile page rather than six separate new pages.

## Current BGLT state

`players.py`'s player profile already has: current handicap + trend, full round-history table (date, season, course, gross/net, hcp, pts, role), career stats, per-season breakdown, hole-by-hole scoring history (avg per hole + eagle/birdie/par/bogey/double **gross** counts across all rounds). That's a strong foundation — the gaps are specifically:
- No **hole-by-hole detail per round** in the consolidated history table (only round totals; hole detail today only exists per-single-matchup via `scores.view`).
- No aggregate **opponent-average** stat (vs. average of all opponents ever faced) — `/compare` only does two *named* players head-to-head.
- No **opponent-history** log (my round vs. that round's specific opponent, chronologically).
- Per-season breakdown isn't cross-tabbed **by course** within a year.
- Round-history table is missing Course Rating/Slope columns.
- Scoring-category counts are gross-only; no **net**-based category counts (relative to net par).

## Decision — extend the profile page, or add a separate "detail" sub-page per player?

**Approach A: Extend the existing player profile page** with additional sections/tabs for the missing pieces (hole-by-hole toggle on the round-history table, a new "vs. Opponents" section, a by-course-by-year table).
- *Tradeoffs:* keeps everything about one player in one place, consistent with how the profile already works; risks the page getting long/cluttered — would need collapsible sections.
- *Effort:* M.

**Approach B: Split into 2-3 dedicated sub-pages** (e.g. `/players/<id>/scoring-detail`, `/players/<id>/opponents`) linked from the profile.
- *Tradeoffs:* keeps the main profile page lean, but fragments "everything about this player" across multiple URLs.
- *Effort:* M, similar total work, different organization.

**Recommendation: lean A** for the smaller additions (course/year cross-tab, net categories, rating/slope columns) and **B** for the two genuinely large new datasets (hole-by-hole full history, opponent-average/history) since those are big enough tables to warrant their own page rather than bloating the profile.

## Open questions for @user

- ~~Is hole-by-hole detail actually wanted?~~ **Answered 2026-07-10 — yes, #1 (Scoring History) and #4 (Scoring by Year), matching GLT's layout.**
- ~~Opponent-average/opponent-history?~~ **Answered 2026-07-10 — declined.** #2, #3, #5, #6 all out of scope.

## Next step

Spec'd — see `Plans/2026-07-10-scoring-history-and-by-year-technical-spec.md`.
